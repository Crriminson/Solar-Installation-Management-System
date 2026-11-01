"""
Purchasing and stock operations for F08.

The one rule this module exists to keep: stock never changes state
without a movement. Every status write below happens beside a
StockMovement row in the same transaction, so the history can always
explain the present count.
"""

from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.catalogue.models import TrackingMethod
from apps.core.api import business_date, check_revision
from apps.core.models import record_event

from .models import (ALLOWED_STOCK_MOVES, BatchLot, GoodsReceipt, MovementReason,
                     PurchaseOrder, PurchaseOrderLine, PurchaseStatus, SerializedUnit,
                     StockMovement, StockStatus, ZERO)


# ============================================================
# Purchasing
# ============================================================

@transaction.atomic
def place_purchase_order(order_id, data, actor):
    """Sends a draft to the supplier. After this the lines are committed to."""
    purchase = _locked_purchase(order_id)
    check_revision(purchase, data)

    if purchase.status != PurchaseStatus.DRAFT:
        raise ValidationError({"status": ["Only a draft purchase order can be placed."]})
    if not purchase.lines.exists():
        raise ValidationError({"lines": ["A purchase order needs at least one line."]})

    _update_purchase(purchase, actor, "placed",
                     status=PurchaseStatus.PLACED, placed_on=business_date())
    return purchase


@transaction.atomic
def cancel_purchase_order(order_id, data, actor):
    purchase = _locked_purchase(order_id)
    check_revision(purchase, data)

    if purchase.receipts.exists():
        raise ValidationError(
            {"status": ["Goods have already been received against this order."]}
        )
    if not data.get("reason", "").strip():
        raise ValidationError({"reason": ["Say why the purchase order is cancelled."]})

    _update_purchase(purchase, actor, "cancelled", reason=data["reason"],
                     status=PurchaseStatus.CANCELLED)
    return purchase


# ============================================================
# Receiving
# ============================================================

@transaction.atomic
def receive_goods(order_id, data, actor):
    """
    Books in what actually turned up.

    Each line creates stock in the shape its product supports: serialized
    products become one unit per serial, bulk products become one lot
    with a quantity. The two are not interchangeable, so asking for the
    wrong one is refused rather than guessed at.
    """
    purchase = _locked_purchase(order_id)

    if purchase.status not in (PurchaseStatus.PLACED, PurchaseStatus.PART_RECEIVED):
        raise ValidationError(
            {"status": ["Goods can only be received against a placed purchase order."]}
        )
    if data["received_on"] > business_date():
        raise ValidationError({"received_on": ["Goods cannot have arrived in the future."]})

    receipt = GoodsReceipt.objects.create(
        purchase_order=purchase,
        delivery_note_reference=data.get("delivery_note_reference", "").strip(),
        received_on=data["received_on"],
        received_by=actor,
        notes=data.get("notes", "").strip(),
    )

    for row in data["lines"]:
        line = (PurchaseOrderLine.objects.select_for_update()
                .select_related("product")
                .filter(pk=row["line"], purchase_order=purchase)
                .first())
        if line is None:
            raise ValidationError({"lines": ["That line is not on this purchase order."]})

        if line.product.tracking_method == TrackingMethod.SERIALIZED:
            quantity = _receive_serialized(line, row, receipt, actor)
        elif line.product.tracking_method == TrackingMethod.BULK:
            quantity = _receive_bulk(line, row, receipt, actor)
        else:
            raise ValidationError(
                {"lines": [f"{line.product.sku} is a service and is never stocked."]}
            )

        if quantity > line.outstanding_quantity:
            raise ValidationError(
                {"lines": [f"Only {line.outstanding_quantity} {line.product.unit} of "
                           f"{line.product.sku} is still outstanding."]}
            )
        PurchaseOrderLine.objects.filter(pk=line.pk).update(
            received_quantity=line.received_quantity + quantity
        )

    _settle_purchase_status(purchase, actor)
    record_event(receipt, "received", actor, after={"reference": receipt.reference})
    return receipt


def _receive_serialized(line, row, receipt, actor):
    """One unit per serial. A blank serial is allowed; a duplicate is not."""
    serials = row.get("serial_numbers")
    if not serials:
        raise ValidationError(
            {"serial_numbers": [f"{line.product.sku} is serialized. Scan each unit."]}
        )

    for serial in serials:
        serial = serial.strip()
        if serial and SerializedUnit.objects.filter(
                product=line.product, serial_number=serial).exists():
            raise ValidationError(
                {"serial_numbers": [f"Serial {serial} is already in stock."]}
            )

        unit = SerializedUnit.objects.create(
            product=line.product,
            goods_receipt=receipt,
            serial_number=serial,
            acquisition_cost=line.unit_cost,
            status=StockStatus.AVAILABLE,
        )
        _write_movement(actor, unit=unit, reason=MovementReason.RECEIPT,
                        from_status="", to_status=StockStatus.AVAILABLE,
                        quantity=Decimal("1.00"))

    return Decimal(len(serials))


def _receive_bulk(line, row, receipt, actor):
    """One lot per batch id. No serial is invented for a length of cable."""
    batch_id = (row.get("batch_id") or "").strip()
    quantity = _as_decimal(row.get("quantity"))

    if not batch_id:
        raise ValidationError(
            {"batch_id": [f"{line.product.sku} is bulk. Scan the batch or container id."]}
        )
    if quantity is None or quantity <= ZERO:
        raise ValidationError({"quantity": ["Record how much arrived."]})

    lot = BatchLot.objects.create(
        product=line.product,
        goods_receipt=receipt,
        batch_id=batch_id,
        quantity=quantity,
        unit=line.product.unit,
        unit_cost=line.unit_cost,
        status=StockStatus.AVAILABLE,
    )
    _write_movement(actor, lot=lot, reason=MovementReason.RECEIPT,
                    from_status="", to_status=StockStatus.AVAILABLE, quantity=quantity)
    return quantity


def _settle_purchase_status(purchase, actor):
    """Fully received when every line is, part received while any remains."""
    lines = purchase.lines.all()
    complete = all(line.received_quantity >= line.quantity for line in lines)
    status = PurchaseStatus.RECEIVED if complete else PurchaseStatus.PART_RECEIVED

    if purchase.status != status:
        _update_purchase(purchase, actor, status, status=status)


# ============================================================
# Stock movement
# ============================================================

@transaction.atomic
def move_stock(actor, *, unit=None, lot=None, to_status, reason,
               quantity=None, order=None, note="", clear_order=False):
    """
    The only way a stock item changes state.

    Locks the item, checks the move is allowed, writes the new status and
    the movement together. Callers in F09 to F11 come through here rather
    than touching status themselves.

    clear_order unlinks the item from its order, for a released
    reservation. The movement still names the order it came back from.
    """
    if (unit is None) == (lot is None):
        raise ValidationError({"stock": ["Name exactly one unit or one lot."]})

    item = (SerializedUnit.objects.select_for_update().get(pk=unit.pk) if unit
            else BatchLot.objects.select_for_update().get(pk=lot.pk))

    if to_status not in ALLOWED_STOCK_MOVES.get(item.status, []):
        raise ValidationError(
            {"status": [f"A {item.get_status_display().lower()} item cannot become "
                        f"{StockStatus(to_status).label.lower()}."]}
        )

    from_status = item.status
    quantity = _as_decimal(quantity)
    moved = quantity if quantity is not None else (
        item.quantity if lot else Decimal("1.00")
    )

    if lot is not None and moved > item.quantity:
        raise ValidationError(
            {"quantity": [f"Only {item.quantity} {item.unit} is in this lot."]}
        )

    fields = {"status": to_status, "updated_at": timezone.now()}
    if order is not None:
        fields["order"] = order
    if clear_order:
        fields["order"] = None

    if unit is not None:
        SerializedUnit.objects.filter(pk=item.pk).update(**fields)
    else:
        # A partial move leaves the rest of the lot where it was.
        remaining = item.quantity - moved
        if remaining > ZERO:
            BatchLot.objects.filter(pk=item.pk).update(quantity=remaining)
            item = BatchLot.objects.create(
                product=item.product, goods_receipt=item.goods_receipt,
                batch_id=item.batch_id, parent_lot=item.parent_lot or item,
                quantity=moved, unit=item.unit, unit_cost=item.unit_cost, **fields,
            )
        else:
            BatchLot.objects.filter(pk=item.pk).update(**fields)

    item.refresh_from_db()
    _write_movement(actor, unit=item if unit else None, lot=None if unit else item,
                    reason=reason, from_status=from_status, to_status=to_status,
                    quantity=moved, order=order, note=note)
    return item


def _write_movement(actor, *, unit=None, lot=None, reason, from_status, to_status,
                    quantity, order=None, note=""):
    return StockMovement.objects.create(
        unit=unit, lot=lot, reason=reason, from_status=from_status,
        to_status=to_status, quantity=quantity, order=order, note=note, moved_by=actor,
    )


# ============================================================
# Helpers
# ============================================================

def _as_decimal(value):
    """
    Accepts a quantity however it arrives.

    Serializers hand over a Decimal, but these services are also called
    directly by F09 and F11, where a string from JSON would otherwise
    blow up on the first comparison.
    """
    if value is None or isinstance(value, Decimal):
        return value
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        raise ValidationError({"quantity": ["That is not a number."]})


def _locked_purchase(order_id):
    purchase = PurchaseOrder.objects.select_for_update().filter(pk=order_id).first()
    if purchase is None:
        raise NotFound()
    return purchase


def _update_purchase(purchase, actor, action, *, reason="", **fields):
    before = {"status": purchase.status, "revision": purchase.revision}
    PurchaseOrder.objects.filter(pk=purchase.pk).update(
        revision=purchase.revision + 1, updated_at=timezone.now(), **fields
    )
    purchase.refresh_from_db()
    record_event(purchase, action, actor, before=before,
                 after={"status": purchase.status, "revision": purchase.revision},
                 reason=reason)
