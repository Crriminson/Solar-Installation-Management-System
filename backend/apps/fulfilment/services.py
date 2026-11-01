"""
Reservation, packing and dispatch operations for F09.

Reservation is the dangerous one. Two warehouse staff picking two
orders at the same moment must not both be handed the same inverter, so
every candidate row is locked and re-read inside the transaction before
it is claimed. A count read before the lock means nothing.

All stock state changes go through inventory.services.move_stock, so
every movement here is recorded like any other.
"""

from decimal import Decimal

from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models import Role
from apps.catalogue.models import Category, TrackingMethod
from apps.core.api import business_date, check_revision
from apps.core.models import record_event
from apps.inventory.models import BatchLot, MovementReason, SerializedUnit, StockStatus
from apps.inventory.services import move_stock
from apps.orders.models import Order, OrderStatus
from apps.warranties.services import issue_warranties

from .models import (ALLOWED_FULFILMENT_MOVES, Fulfilment, FulfilmentStatus, PackingLine,
                     ScanEvent, ZERO)

ONE = Decimal("1.00")


# ============================================================
# Opening a fulfilment
# ============================================================

@transaction.atomic
def open_fulfilment(order_id, actor):
    """
    Builds the packing checklist from the accepted order, and reserves.

    Calling again returns the existing fulfilment: the checklist comes
    from an immutable quotation revision, so there is nothing to refresh.
    If nothing is reserved yet, opening again tries again, so stock that
    arrived after a shortage is claimed by opening the list.
    """
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        raise NotFound()

    existing = Fulfilment.objects.filter(order=order).first()
    if existing is not None:
        if existing.status in (FulfilmentStatus.PENDING, FulfilmentStatus.BLOCKED):
            return reserve_stock(existing.pk, actor)
        return existing

    if order.status == OrderStatus.CANCELLED:
        raise ValidationError({"order": ["A cancelled order is not packed."]})

    lines = _physical_lines(order)
    if not lines:
        raise ValidationError({"order": ["This order has nothing physical to pack."]})

    fulfilment = _create_checklist(order, lines, actor)

    # Reserve straight away. A warehouse worker should meet the order
    # either ready to pack or blocked, never sitting at Pending waiting
    # for somebody to press a button they did not know about.
    return reserve_stock(fulfilment.pk, actor)


def prepare_for_order(order, actor):
    """
    The warehouse requirement, created when the order is confirmed (F07).

    This runs inside the confirmation, so it must never undo it. An order
    with nothing physical has no packing list. A shortage is not a
    failure: it blocks the list and names what to buy. A reservation that
    does fail, because another order took the stock mid-claim, is rolled
    back to a savepoint and leaves the list Pending for the warehouse to
    open again.
    """
    lines = _physical_lines(order)
    if not lines:
        return None

    fulfilment = _create_checklist(order, lines, actor)
    try:
        with transaction.atomic():
            return reserve_stock(fulfilment.pk, actor)
    except ValidationError as error:
        record_event(fulfilment, "reservation_deferred", actor, reason=str(error.detail))
        return fulfilment


def release_for_cancelled_order(order, actor, reason):
    """
    Puts a cancelled order's reserved stock back on the shelf.

    Every unit and lot goes back through move_stock, so the release is a
    recorded movement like the reservation was, and loses its link to the
    order. Refused once the goods have left: that is a return.
    """
    fulfilment = Fulfilment.objects.select_for_update().filter(order=order).first()
    if fulfilment is None:
        return
    _require_move(fulfilment, FulfilmentStatus.CANCELLED)

    note = f"Released: {order.reference} was cancelled"
    for unit in _reserved_units(fulfilment):
        move_stock(actor, unit=unit, to_status=StockStatus.AVAILABLE,
                   reason=MovementReason.RELEASE, order=order, clear_order=True, note=note)
    for lot in _reserved_lots(fulfilment):
        move_stock(actor, lot=lot, to_status=StockStatus.AVAILABLE,
                   reason=MovementReason.RELEASE, order=order, clear_order=True, note=note)

    _move(fulfilment, FulfilmentStatus.CANCELLED, actor)
    record_event(fulfilment, "released", actor, reason=reason)


def _physical_lines(order):
    """
    The quotation lines that go in a box.

    Labour is not stocked, so it is never on a packing list. Checked on
    both the category and the tracking method: a product mis-set on one
    must not put a line on the checklist that nobody can ever scan.
    """
    return list(order.quotation.lines.select_related("product").exclude(
        models.Q(product__tracking_method=TrackingMethod.SERVICE)
        | models.Q(product__category=Category.SERVICE)
    ))


def _create_checklist(order, lines, actor):
    fulfilment = Fulfilment.objects.create(order=order)

    for line in lines:
        PackingLine.objects.create(
            fulfilment=fulfilment,
            product=line.product,
            sku=line.sku,
            description=line.description,
            unit=line.unit,
            tracking_method=line.product.tracking_method,
            required_quantity=line.quantity,
        )

    record_event(fulfilment, "opened", actor,
                 after={"order": order.reference, "lines": len(lines)})
    return fulfilment


# ============================================================
# Reservation
# ============================================================

@transaction.atomic
def reserve_stock(fulfilment_id, actor):
    """
    Claims the stock this order needs, or blocks and says what is short.

    Two passes on purpose. The first only counts: if any line cannot be
    filled, the order blocks without a single unit being claimed, so a
    shortage on one line never strands stock that another order could
    have used. Only once every line can be met does the second pass take
    anything.
    """
    fulfilment = _locked_fulfilment(fulfilment_id)
    _require_move(fulfilment, FulfilmentStatus.RESERVED)

    lines = list(fulfilment.lines.select_for_update().select_related("product"))

    shortages = [
        f"{line.sku}: {line.required_quantity - _available_quantity(line)} "
        f"{line.unit} short"
        for line in lines
        if _available_quantity(line) < line.required_quantity
    ]
    if shortages:
        reason = ("Short of stock. Raise a purchase order for: "
                  + "; ".join(shortages) + ".")
        _move(fulfilment, FulfilmentStatus.BLOCKED, actor, blocked_reason=reason)
        return fulfilment

    for line in lines:
        claimed = (_reserve_units(line, fulfilment, actor)
                   if line.tracking_method == TrackingMethod.SERIALIZED
                   else _reserve_lots(line, fulfilment, actor))

        if claimed < line.required_quantity:
            # Somebody else took it between the count and the claim. Raising
            # rolls the whole reservation back; the warehouse tries again.
            raise ValidationError({"stock": [
                f"{line.sku} was taken while this order was being reserved. "
                "Reserve again."
            ]})
        PackingLine.objects.filter(pk=line.pk).update(reserved_quantity=claimed)

    _move(fulfilment, FulfilmentStatus.RESERVED, actor, blocked_reason="")
    return fulfilment


def _available_quantity(line):
    """How much of this line is on the shelf and unclaimed."""
    if line.tracking_method == TrackingMethod.SERIALIZED:
        return Decimal(SerializedUnit.objects.filter(
            product=line.product, status=StockStatus.AVAILABLE).count())

    total = BatchLot.objects.filter(
        product=line.product, status=StockStatus.AVAILABLE
    ).aggregate(total=models.Sum("quantity"))["total"]
    return total or ZERO


def _reserve_units(line, fulfilment, actor):
    """Claims whole units, oldest first, locking each before taking it."""
    wanted = int(line.required_quantity)
    candidates = (SerializedUnit.objects
                  .select_for_update(skip_locked=True)
                  .filter(product=line.product, status=StockStatus.AVAILABLE)
                  .order_by("id")[:wanted])

    claimed = 0
    for unit in list(candidates):
        move_stock(actor, unit=unit, to_status=StockStatus.RESERVED,
                   reason=MovementReason.RESERVATION, order=fulfilment.order,
                   note=f"Reserved for {fulfilment.order.reference}")
        claimed += 1
    return Decimal(claimed)


def _reserve_lots(line, fulfilment, actor):
    """Takes from lots until the quantity is met, splitting the last one."""
    outstanding = line.required_quantity
    lots = (BatchLot.objects
            .select_for_update(skip_locked=True)
            .filter(product=line.product, status=StockStatus.AVAILABLE, quantity__gt=ZERO)
            .order_by("id"))

    claimed = ZERO
    for lot in list(lots):
        if outstanding <= ZERO:
            break
        take = min(lot.quantity, outstanding)
        move_stock(actor, lot=lot, to_status=StockStatus.RESERVED,
                   reason=MovementReason.RESERVATION, quantity=take,
                   order=fulfilment.order,
                   note=f"Reserved for {fulfilment.order.reference}")
        claimed += take
        outstanding -= take
    return claimed


# ============================================================
# Packing
# ============================================================

@transaction.atomic
def scan_item(fulfilment_id, data, actor):
    """
    Confirms one physical item into the box.

    Every rejection the spec asks for lives here: the wrong product, a
    unit held for another order, an asset already gone out, the same
    unit twice, and a manual entry with no reason behind it.
    """
    fulfilment = _locked_fulfilment(fulfilment_id)
    if fulfilment.status not in (FulfilmentStatus.RESERVED, FulfilmentStatus.PACKED):
        raise ValidationError(
            {"status": ["Reserve the stock before packing it."]}
        )

    manual = data.get("entered_manually", False)
    reason = data.get("manual_reason", "").strip()
    if manual:
        if not actor.has_any_role(Role.OPERATIONS_MANAGER):
            raise ValidationError(
                {"entered_manually": ["Only an operations manager may enter an item by hand."]}
            )
        if not reason:
            raise ValidationError(
                {"manual_reason": ["Say why this item could not be scanned."]}
            )

    code = data["code"].strip()
    unit = (SerializedUnit.objects.select_for_update()
            .filter(models.Q(serial_number=code) | models.Q(asset_id=code)).first()
            if code else None)

    if unit is not None:
        return _scan_unit(fulfilment, unit, manual, reason, actor)
    return _scan_lot(fulfilment, code, data, manual, reason, actor)


def _scan_unit(fulfilment, unit, manual, reason, actor):
    line = fulfilment.lines.select_for_update().filter(product=unit.product).first()
    if line is None:
        raise ValidationError(
            {"code": [f"{unit.product.sku} is not on this order."]}
        )

    if unit.status in (StockStatus.DISPATCHED, StockStatus.DELIVERED,
                       StockStatus.INSTALLED):
        raise ValidationError(
            {"code": [f"{unit.asset_id} has already left the warehouse."]}
        )
    # Must be held for *this* order. A unit reserved against nothing is
    # as wrong as one reserved against somebody else: neither was picked
    # for this box.
    if unit.order_id != fulfilment.order_id:
        raise ValidationError({"code": [
            f"{unit.asset_id} is held for another order."
            if unit.order_id else f"{unit.asset_id} is not reserved for this order."
        ]})
    if unit.status != StockStatus.RESERVED:
        raise ValidationError(
            {"code": [f"{unit.asset_id} is {unit.get_status_display().lower()}, not reserved "
                      "for this order."]}
        )
    if ScanEvent.objects.filter(line=line, unit=unit).exists():
        raise ValidationError({"code": [f"{unit.asset_id} is already in the box."]})
    if line.is_complete:
        raise ValidationError(
            {"code": [f"{line.sku} is already fully packed."]}
        )

    scan = ScanEvent.objects.create(
        line=line, unit=unit, quantity=ONE,
        entered_manually=manual, manual_reason=reason, scanned_by=actor,
    )
    PackingLine.objects.filter(pk=line.pk).update(
        packed_quantity=line.packed_quantity + ONE
    )
    record_event(scan, "scanned", actor,
                 after={"asset": unit.asset_id, "manual": manual}, reason=reason)
    return scan


def _scan_lot(fulfilment, code, data, manual, reason, actor):
    quantity = data.get("quantity")
    if quantity is None or quantity <= ZERO:
        raise ValidationError(
            {"quantity": ["A batch needs a counted quantity as well as its id."]}
        )

    lot = (BatchLot.objects.select_for_update()
           .filter(batch_id=code, order=fulfilment.order, status=StockStatus.RESERVED)
           .first())
    if lot is None:
        raise ValidationError(
            {"code": [f"No batch {code} is reserved for this order."]}
        )

    line = fulfilment.lines.select_for_update().filter(product=lot.product).first()
    if line is None:
        raise ValidationError({"code": [f"{lot.product.sku} is not on this order."]})
    if quantity > line.outstanding_quantity:
        raise ValidationError(
            {"quantity": [f"Only {line.outstanding_quantity} {line.unit} of {line.sku} "
                          "is still needed."]}
        )

    scan = ScanEvent.objects.create(
        line=line, lot=lot, quantity=quantity,
        entered_manually=manual, manual_reason=reason, scanned_by=actor,
    )
    PackingLine.objects.filter(pk=line.pk).update(
        packed_quantity=line.packed_quantity + quantity
    )
    record_event(scan, "scanned", actor,
                 after={"batch": lot.batch_id, "quantity": str(quantity),
                        "manual": manual}, reason=reason)
    return scan


@transaction.atomic
def close_packing(fulfilment_id, data, actor):
    """Seals the box. Refused while anything on the checklist is missing."""
    fulfilment = _locked_fulfilment(fulfilment_id)
    check_revision(fulfilment, data)
    _require_move(fulfilment, FulfilmentStatus.PACKED)

    missing = fulfilment.shortages()
    if missing:
        raise ValidationError({"lines": [
            "Not everything is packed: "
            + "; ".join(f"{line.sku} needs {line.outstanding_quantity} {line.unit}"
                        for line in missing)
        ]})

    _move(fulfilment, FulfilmentStatus.PACKED, actor)
    return fulfilment


# ============================================================
# Dispatch and delivery
# ============================================================

@transaction.atomic
def dispatch(fulfilment_id, data, actor):
    """
    Sends the order out. Both gates have to be open: money and stock.

    The money gate is the order's, computed from cleared payments only
    (F07). The stock gate is this fulfilment being packed in full.
    """
    fulfilment = _locked_fulfilment(fulfilment_id)
    check_revision(fulfilment, data)
    _require_move(fulfilment, FulfilmentStatus.DISPATCHED)

    order = Order.objects.select_for_update().get(pk=fulfilment.order_id)
    if not order.dispatch_allowed:
        raise ValidationError({"order": [
            f"Dispatch is held until {order.advance_payable} has cleared. "
            f"{order.cleared_total()} has cleared so far."
        ]})

    for unit in _reserved_units(fulfilment):
        move_stock(actor, unit=unit, to_status=StockStatus.DISPATCHED,
                   reason=MovementReason.DISPATCH, order=order)
    for lot in _reserved_lots(fulfilment):
        move_stock(actor, lot=lot, to_status=StockStatus.DISPATCHED,
                   reason=MovementReason.DISPATCH, order=order)

    _move(fulfilment, FulfilmentStatus.DISPATCHED, actor,
          dispatched_by=actor, dispatched_at=timezone.now(),
          carrier_reference=data.get("carrier_reference", "").strip())
    return fulfilment


@transaction.atomic
def deliver(fulfilment_id, data, actor):
    """
    Records that the customer has the equipment.

    This is the moment that matters downstream: it makes the balance due
    (D024) and it is what starts every warranty (F12). Packing and
    dispatch do neither.
    """
    fulfilment = _locked_fulfilment(fulfilment_id)
    check_revision(fulfilment, data)
    _require_move(fulfilment, FulfilmentStatus.DELIVERED)

    if not data.get("received_by_name", "").strip():
        raise ValidationError(
            {"received_by_name": ["Record who took delivery."]}
        )
    delivered_at = data["delivered_at"]
    if delivered_at > timezone.now():
        raise ValidationError({"delivered_at": ["Delivery cannot be in the future."]})

    order = Order.objects.select_for_update().get(pk=fulfilment.order_id)

    # Every warranty starts from this date and none can be edited after,
    # so an impossible one stops here. Not compared with dispatched_at:
    # that is when dispatch was keyed in, which can be after a true
    # delivery time if the warehouse catches up late (D052).
    if delivered_at < order.confirmed_at:
        raise ValidationError(
            {"delivered_at": ["Delivery cannot be before the order was confirmed."]}
        )

    for unit in _dispatched_units(fulfilment):
        move_stock(actor, unit=unit, to_status=StockStatus.DELIVERED,
                   reason=MovementReason.DELIVERY, order=order)
        SerializedUnit.objects.filter(pk=unit.pk).update(
            customer=order.customer, site=order.site
        )
    for lot in _dispatched_lots(fulfilment):
        move_stock(actor, lot=lot, to_status=StockStatus.DELIVERED,
                   reason=MovementReason.DELIVERY, order=order)

    _move(fulfilment, FulfilmentStatus.DELIVERED, actor,
          delivered_at=delivered_at,
          delivery_recorded_at=timezone.now(),
          delivered_by=actor,
          received_by_name=data["received_by_name"].strip(),
          delivery_notes=data.get("delivery_notes", "").strip())

    # Same transaction: a delivery with no cover behind it must not commit.
    issue_warranties(fulfilment, actor)

    # The balance falls due now, not at installation acceptance (D024).
    Order.objects.filter(pk=order.pk).update(
        status=OrderStatus.DELIVERED,
        balance_due_on=business_date(),
        revision=order.revision + 1,
    )
    record_event(order, "delivered", actor,
                 after={"balance_due_on": str(business_date())})
    return fulfilment


# ============================================================
# Helpers
# ============================================================

def _reserved_units(fulfilment):
    return SerializedUnit.objects.select_for_update().filter(
        order=fulfilment.order, status=StockStatus.RESERVED)


def _reserved_lots(fulfilment):
    return BatchLot.objects.select_for_update().filter(
        order=fulfilment.order, status=StockStatus.RESERVED)


def _dispatched_units(fulfilment):
    return SerializedUnit.objects.select_for_update().filter(
        order=fulfilment.order, status=StockStatus.DISPATCHED)


def _dispatched_lots(fulfilment):
    return BatchLot.objects.select_for_update().filter(
        order=fulfilment.order, status=StockStatus.DISPATCHED)


def _locked_fulfilment(fulfilment_id):
    fulfilment = (Fulfilment.objects.select_for_update()
                  .select_related("order")
                  .filter(pk=fulfilment_id).first())
    if fulfilment is None:
        raise NotFound()
    return fulfilment


def _require_move(fulfilment, target):
    if target not in ALLOWED_FULFILMENT_MOVES.get(fulfilment.status, []):
        raise ValidationError({"status": [
            f"A {fulfilment.get_status_display().lower()} fulfilment cannot become "
            f"{FulfilmentStatus(target).label.lower()}."
        ]})


def _move(fulfilment, status, actor, **fields):
    before = {"status": fulfilment.status, "revision": fulfilment.revision}
    Fulfilment.objects.filter(pk=fulfilment.pk).update(
        status=status, revision=fulfilment.revision + 1,
        updated_at=timezone.now(), **fields,
    )
    fulfilment.refresh_from_db()
    record_event(fulfilment, status, actor, before=before,
                 after={"status": status, "revision": fulfilment.revision})
