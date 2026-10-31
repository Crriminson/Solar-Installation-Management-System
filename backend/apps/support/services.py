"""
Ticket operations for F13.

Everything runs with the ticket row locked, so two people working one
ticket cannot both pass a check that only one of them should.

Two rules are worth stating here. Coverage is judged once, on the
complaint's recorded time, and stored on the ticket; waiting for a
technician can never change it (D021). And a line is billed only by
being attached to an invoice, so finishing work twice, or reopening a
ticket, can never charge the same line again.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models import Role
from apps.catalogue.models import Category, Product, TrackingMethod
from apps.core.api import business_date, check_revision
from apps.core.models import record_event
from apps.customers.models import Customer
from apps.inventory.models import MovementReason, SerializedUnit, StockStatus
from apps.inventory.services import move_stock
from apps.orders.models import InvoiceKind
from apps.orders.services import issue_invoice
from apps.scheduling.models import Job, JobStatus
from apps.scheduling.services import begin_visit, create_job, finish_visit
from apps.warranties.services import record_replacement

from .models import (ALLOWED_TICKET_MOVES, Assessment, Disposition, EstimateLine, EstimateStatus,
                     RepairEstimate, Replacement, ServiceTicket, TicketAsset, TicketStatus,
                     WorkLine, ZERO)

User = get_user_model()

PENNY = Decimal("0.01")
PERCENT = Decimal("100")

# Units a customer can have a problem with.
WITH_THE_CUSTOMER = [StockStatus.DELIVERED, StockStatus.INSTALLED]


def rounded(amount):
    """INR to two places, half up, the same way quotation lines round."""
    return amount.quantize(PENNY, rounding=ROUND_HALF_UP)


# ============================================================
# Raising a ticket
# ============================================================

@transaction.atomic
def raise_ticket(data, actor):
    """
    Opens a ticket and assesses each unit against its warranty.

    The actor is locked so a double-submitted form finds the first ticket
    by its key rather than racing it. The complaint time is always the
    server's. A date the customer claims is kept, but it sends the unit
    to review rather than deciding anything.
    """
    User.objects.select_for_update().get(pk=actor.pk)

    key = data.get("idempotency_key", "").strip()
    if key:
        existing = ServiceTicket.objects.filter(idempotency_key=key).first()
        if existing is not None:
            return existing

    customer = Customer.objects.filter(pk=data["customer"]).first()
    if customer is None:
        raise ValidationError({"customer": ["No customer with that id."]})

    now = timezone.now()
    claimed = data.get("claimed_complaint_at")
    if claimed is not None and claimed > now:
        raise ValidationError({"claimed_complaint_at": ["That is in the future."]})

    units = _affected_units(customer, data["units"])
    first = units[0]
    if len({unit.order_id for unit in units}) > 1:
        raise ValidationError({"units": ["Raise one ticket per order."]})

    ticket = ServiceTicket.objects.create(
        customer=customer, site=first.site, order=first.order,
        fault_description=data["fault_description"].strip(),
        fault_code=data.get("fault_code", "").strip(),
        priority=data.get("priority", ServiceTicket._meta.get_field("priority").default),
        complaint_at=now, claimed_complaint_at=claimed,
        idempotency_key=key, created_by=actor,
    )
    for unit in units:
        warranty, assessment = _assess(unit, customer, now, claimed)
        TicketAsset.objects.create(
            ticket=ticket, unit=unit, warranty=warranty, assessment=assessment
        )

    record_event(ticket, "raised", actor, after={
        "reference": ticket.reference, "complaint_at": str(now),
        "claimed_complaint_at": str(claimed) if claimed else "",
    })
    return ticket


def _affected_units(customer, unit_ids):
    units = list(SerializedUnit.objects
                 .filter(pk__in=unit_ids, customer=customer, status__in=WITH_THE_CUSTOMER)
                 .select_related("site", "order"))
    if len(units) != len(set(unit_ids)):
        raise ValidationError(
            {"units": ["Every unit must be equipment this customer has."]}
        )
    return units


def _assess(unit, customer, complaint_at, claimed):
    """
    Judged on the recorded complaint, and only on that.

    A newer warranty on the same unit wins: a resold unit's old cover
    belongs to its previous owner, so it is looked up by this customer.
    """
    warranty = unit.warranties.filter(customer=customer).order_by("-id").first()
    if claimed is not None:
        return warranty, Assessment.REVIEW
    if warranty is not None and warranty.covers(business_date(complaint_at)):
        return warranty, Assessment.COVERED
    return warranty, Assessment.NOT_COVERED


@transaction.atomic
def review_assessment(ticket_id, data, actor):
    """
    An authorized decision on a disputed or backdated claim.

    Stops once work has started: by then a customer may have approved and
    paid on the assessment as it stood.
    """
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)
    if ticket.status not in (TicketStatus.NEW, TicketStatus.DIAGNOSED):
        raise ValidationError({"status": ["Coverage cannot change once work has started."]})

    reason = data.get("reason", "").strip()
    if not reason:
        raise ValidationError({"reason": ["Say why this decision was reached."]})

    asset = _ticket_asset(ticket, data["asset"])
    if data["assessment"] == Assessment.COVERED and asset.warranty_id is None:
        raise ValidationError({"assessment": ["This unit has no warranty to claim on."]})

    before = {"assessment": asset.assessment}
    asset.assessment = data["assessment"]
    asset.review_reason = reason
    asset.reviewed_by = actor
    asset.reviewed_at = timezone.now()
    asset.save()

    _update(ticket, actor, "assessment_reviewed", reason=reason)
    record_event(asset, "reviewed", actor, before=before,
                 after={"assessment": asset.assessment}, reason=reason)
    return ticket


# ============================================================
# Ownership and blocks
# ============================================================

@transaction.atomic
def assign_ticket(ticket_id, data, actor):
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)

    owner = User.objects.filter(pk=data["owner"]).first()
    if owner is None or not owner.is_active_staff:
        raise ValidationError({"owner": ["No active staff member with that id."]})

    _update(ticket, actor, "assigned", owner=owner)
    return ticket


@transaction.atomic
def block_ticket(ticket_id, data, actor):
    """Waiting on a part or an approval is recorded against somebody (D048)."""
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)

    reason = data.get("reason", "").strip()
    if not reason:
        raise ValidationError({"reason": ["Say what the ticket is waiting on."]})
    owner = User.objects.filter(pk=data.get("owner")).first()
    if owner is None:
        raise ValidationError({"owner": ["Name who is going to clear this."]})

    _update(ticket, actor, "blocked", reason=reason, blocked_reason=reason, blocked_owner=owner)
    return ticket


@transaction.atomic
def unblock_ticket(ticket_id, data, actor):
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)
    _update(ticket, actor, "unblocked", blocked_reason="", blocked_owner=None)
    return ticket


# ============================================================
# The visit and the diagnosis
# ============================================================

@transaction.atomic
def book_visit(ticket_id, data, actor):
    """A visit is an F10 job, so overlap rules apply exactly as elsewhere."""
    ticket = _locked_ticket(ticket_id)
    if ticket.status == TicketStatus.CLOSED:
        raise ValidationError({"status": ["Reopen the ticket before booking a visit."]})

    job = create_job({
        "kind": "service", "site": ticket.site_id, "order": ticket.order_id,
        "ticket": ticket.pk, "starts_at": data["starts_at"], "ends_at": data["ends_at"],
        "notes": data.get("notes", "") or f"Service visit for {ticket.reference}",
        "technicians": data["technicians"],
    }, actor)
    _update(ticket, actor, "visit_booked", blocked_reason="", blocked_owner=None)
    return job


@transaction.atomic
def diagnose(ticket_id, data, actor):
    """
    Records what a technician found on a visit.

    Nothing chargeable or covered goes ahead without this, so it has to
    come from a real visit on this ticket, and from the crew on it.
    """
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)
    _require_move(ticket, TicketStatus.DIAGNOSED)

    job = (Job.objects.select_for_update(of=("self",)).filter(pk=data["job"], ticket=ticket)
           .exclude(status=JobStatus.CANCELLED).first())
    if job is None:
        raise ValidationError({"job": ["Diagnosis comes from a visit on this ticket."]})
    if not (is_office(actor) or job.assignments.filter(technician=actor).exists()):
        raise ValidationError({"job": ["Only the crew on this visit can record what it found."]})

    findings = data.get("findings", "").strip()
    recommendation = data.get("recommendation", "").strip()
    if not findings or not recommendation:
        raise ValidationError(
            {"recommendation": ["Record what was found and what work is recommended."]}
        )

    begin_visit(job, actor)
    _update(ticket, actor, "diagnosed", status=TicketStatus.DIAGNOSED, findings=findings,
            recommendation=recommendation, diagnosed_by=actor, diagnosed_at=timezone.now())
    return ticket


# ============================================================
# Estimates
# ============================================================

@transaction.atomic
def create_estimate(ticket_id, data, actor):
    """
    Prices work on uncovered equipment from the current catalogue.

    A new estimate replaces any live one, which is how scope grows: the
    old approval stops counting and the customer decides afresh.
    """
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)

    if ticket.status not in (TicketStatus.DIAGNOSED, TicketStatus.IN_PROGRESS):
        raise ValidationError({"status": ["Estimates follow a diagnosis."]})
    if not ticket.assets.filter(assessment=Assessment.NOT_COVERED).exists():
        raise ValidationError({"status": ["Covered work needs no estimate."]})

    priced = [_price_line(row) for row in data["lines"]]
    net = sum((line["net_excl_tax"] for line in priced), ZERO)
    tax = sum((line["tax_amount"] for line in priced), ZERO)

    live = ticket.estimates.filter(
        status__in=[EstimateStatus.PENDING, EstimateStatus.APPROVED])
    live.update(status=EstimateStatus.SUPERSEDED)

    latest = ticket.estimates.order_by("-number").first()
    estimate = RepairEstimate.objects.create(
        ticket=ticket, number=latest.number + 1 if latest else 1,
        net_excl_tax=net, tax_amount=tax, gross_incl_tax=net + tax, recorded_by=actor,
    )
    EstimateLine.objects.bulk_create([EstimateLine(estimate=estimate, **line) for line in priced])

    _update(ticket, actor, "estimated")
    return estimate


def _price_line(row):
    product = _chargeable_product(row["product"])
    price = product.current_price().selling_price_excl_tax
    quantity = row["quantity"]
    net = rounded(quantity * price)
    return {
        "product": product, "sku": product.sku, "description": product.name,
        "unit": product.unit, "quantity": quantity, "unit_price_excl_tax": price,
        "gst_rate_percent": product.gst_rate_percent, "net_excl_tax": net,
        "tax_amount": rounded(net * product.gst_rate_percent / PERCENT),
    }


def _chargeable_product(product_id):
    product = Product.objects.prefetch_related("prices").filter(pk=product_id).first()
    if product is None:
        raise ValidationError({"product": ["No product with that id."]})
    if product.current_price() is None:
        raise ValidationError({"product": [f"{product.sku} has no selling price."]})
    return product


@transaction.atomic
def decide_estimate(ticket_id, data, actor):
    """Approval is a decision with a name and a time; no signature (F13)."""
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)

    estimate = ticket.estimates.filter(status=EstimateStatus.PENDING).first()
    if estimate is None:
        raise ValidationError({"estimate": ["No estimate is awaiting a decision."]})

    name = data.get("customer_name", "").strip()
    if not name:
        raise ValidationError({"customer_name": ["Record who decided."]})

    status = EstimateStatus.APPROVED if data["approved"] else EstimateStatus.DECLINED
    RepairEstimate.objects.filter(pk=estimate.pk).update(
        status=status, decided_by_name=name, decided_at=timezone.now()
    )
    _update(ticket, actor, f"estimate_{status}", reason=name)
    return ticket


def _approved_estimate(ticket):
    return ticket.estimates.filter(status=EstimateStatus.APPROVED).first()


# ============================================================
# Doing the work
# ============================================================

@transaction.atomic
def start_work(ticket_id, data, actor):
    """Both gates from the spec: a diagnosis, and the customer's approval."""
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)
    _require_move(ticket, TicketStatus.IN_PROGRESS)

    assessments = set(ticket.assets.values_list("assessment", flat=True))
    if Assessment.REVIEW in assessments:
        raise ValidationError({"assessment": ["Coverage is waiting on authorized review."]})
    if Assessment.NOT_COVERED in assessments and _approved_estimate(ticket) is None:
        raise ValidationError(
            {"estimate": ["The customer has to approve an estimate before work starts."]}
        )

    _update(ticket, actor, "work_started", status=TicketStatus.IN_PROGRESS)
    return ticket


@transaction.atomic
def add_work_line(ticket_id, data, actor):
    ticket = _locked_ticket(ticket_id)
    _require_working(ticket)
    return _record_line(ticket, _ticket_asset(ticket, data["asset"]),
                        _chargeable_product(data["product"]), data["quantity"], actor)


def _record_line(ticket, asset, product, quantity, actor, *, unit_cost=None):
    """
    Charges what uncovered work costs and zero for covered work.

    Uncovered lines are capped by the approved estimate, because exceeding
    approved scope needs a fresh approval. Internal cost is recorded either
    way. Labour's comes from time entries, so it stays zero here.
    """
    price = product.current_price()
    if asset.is_covered:
        net, tax = ZERO, ZERO
    else:
        net = rounded(quantity * price.selling_price_excl_tax)
        tax = rounded(net * product.gst_rate_percent / PERCENT)
        _require_within_scope(ticket, net + tax)

    if unit_cost is None:
        is_labour = product.category == Category.SERVICE
        unit_cost = ZERO if is_labour else (price.purchase_cost_excl_tax or ZERO)

    line = WorkLine.objects.create(
        ticket=ticket, asset=asset, product=product, sku=product.sku,
        description=product.name, unit=product.unit, quantity=quantity,
        charge_excl_tax=net, charge_tax=tax, unit_cost=unit_cost, recorded_by=actor,
    )
    record_event(line, "recorded", actor, after={
        "sku": product.sku, "quantity": str(quantity), "charge_excl_tax": str(net),
    })
    return line


def _require_within_scope(ticket, adding_incl_tax):
    approved = _approved_estimate(ticket)
    if approved is None:
        raise ValidationError(
            {"estimate": ["The customer has to approve this work first."]}
        )

    totals = ticket.work_lines.filter(voided_reason="").aggregate(
        net=models.Sum("charge_excl_tax"), tax=models.Sum("charge_tax"))
    spent = (totals["net"] or ZERO) + (totals["tax"] or ZERO)
    if spent + adding_incl_tax > approved.gross_incl_tax:
        raise ValidationError({"estimate": [
            f"That goes past the {approved.gross_incl_tax} the customer approved. "
            "Raise a new estimate for their approval first."
        ]})


@transaction.atomic
def void_work_line(ticket_id, data, actor):
    """Corrects a mis-entry. A billed line is past this: use a refund."""
    ticket = _locked_ticket(ticket_id)
    _require_working(ticket)

    line = (WorkLine.objects.select_for_update()
            .filter(pk=data["line"], ticket=ticket, voided_reason="").first())
    if line is None:
        raise ValidationError({"line": ["No open line with that id on this ticket."]})
    if line.invoice_id is not None:
        raise ValidationError({"line": ["This line has been invoiced."]})
    reason = data.get("reason", "").strip()
    if not reason:
        raise ValidationError({"reason": ["Say why this line is being voided."]})
    if Replacement.objects.filter(ticket=ticket, asset=line.asset, new_unit__product=line.product).exists():
        raise ValidationError({"line": ["This line is a replacement unit already fitted."]})

    WorkLine.objects.filter(pk=line.pk).update(voided_reason=reason)
    record_event(line, "voided", actor, reason=reason)
    return ticket


# ============================================================
# Replacement
# ============================================================

@transaction.atomic
def replace_unit(ticket_id, data, actor):
    """
    Swaps a failed unit for a new one from stock.

    Issues the new unit through every stock state, so its movements read
    like any other, then returns or quarantines the old one. A covered
    swap moves the warranty across; a paid one has none to move. The
    warranty row is locked before the unit, as record_replacement expects.
    """
    ticket = _locked_ticket(ticket_id)
    _require_working(ticket)

    asset = _ticket_asset(ticket, data["asset"])
    if Replacement.objects.filter(asset=asset).exists():
        raise ValidationError({"asset": ["This unit has already been replaced."]})
    reason = data.get("reason", "").strip()
    if not reason:
        raise ValidationError({"reason": ["Say why this unit is being replaced."]})

    new_unit = _unit_from_stock(data["code"])
    if not asset.is_covered and new_unit.product.current_price() is None:
        raise ValidationError({"code": [f"{new_unit.product.sku} has no selling price."]})

    # Priced first, so an uncovered swap past the approved scope stops
    # here with nothing moved.
    _record_line(ticket, asset, new_unit.product, Decimal("1.00"), actor,
                 unit_cost=new_unit.acquisition_cost)

    new_unit = _issue_to_customer(new_unit, ticket, actor)
    old_unit = _take_back(asset.unit, data["disposition"], ticket, actor)

    now = timezone.now()
    new_warranty = None
    if asset.is_covered:
        new_warranty = record_replacement(asset.warranty_id, new_unit.pk, {
            "complaint_at": ticket.complaint_at, "replaced_at": now, "reason": reason,
            "reviewed": asset.reviewed_by_id is not None,
        }, actor)

    replacement = Replacement.objects.create(
        ticket=ticket, asset=asset, old_unit=old_unit, new_unit=new_unit,
        disposition=data["disposition"], new_warranty=new_warranty, reason=reason,
        replaced_at=now, recorded_by=actor,
    )
    _update(ticket, actor, "unit_replaced", reason=reason)
    return replacement


def _unit_from_stock(code):
    unit = (SerializedUnit.objects.select_for_update(of=("self",))
            .select_related("product")
            .filter(models.Q(serial_number=code.strip()) | models.Q(asset_id=code.strip()))
            .first())
    if unit is None:
        raise ValidationError({"code": [f"No unit matches {code}."]})
    if unit.status != StockStatus.AVAILABLE:
        raise ValidationError(
            {"code": [f"{unit.asset_id} is {unit.get_status_display().lower()}, not in stock."]}
        )
    if unit.product.tracking_method != TrackingMethod.SERIALIZED:
        raise ValidationError({"code": [f"{unit.asset_id} is not a serialized product."]})
    return unit


def _issue_to_customer(unit, ticket, actor):
    """Walks the new unit out of the door. No state is skipped or forged."""
    for status, reason in ((StockStatus.RESERVED, MovementReason.RESERVATION),
                           (StockStatus.DISPATCHED, MovementReason.DISPATCH),
                           (StockStatus.DELIVERED, MovementReason.DELIVERY),
                           (StockStatus.INSTALLED, MovementReason.INSTALLATION)):
        unit = move_stock(actor, unit=unit, to_status=status, reason=reason, order=ticket.order,
                          note=f"Replacement on {ticket.reference}")

    SerializedUnit.objects.filter(pk=unit.pk).update(customer=ticket.customer, site=ticket.site)
    unit.refresh_from_db()
    return unit


def _take_back(unit, disposition, ticket, actor):
    note = f"Taken back on {ticket.reference}"
    unit = move_stock(actor, unit=unit, to_status=StockStatus.RETURNED,
                      reason=MovementReason.RETURN, note=note)
    if disposition == Disposition.QUARANTINED:
        unit = move_stock(actor, unit=unit, to_status=StockStatus.QUARANTINED,
                          reason=MovementReason.QUARANTINE, note=note)
    return unit


# ============================================================
# Finishing and closing
# ============================================================

@transaction.atomic
def finish_work(ticket_id, data, actor):
    """
    Ends the work and bills it, then waits for the customer.

    Finishing is not closing: only the customer's word closes a ticket.
    Lines already on an invoice are skipped, so going round again after a
    reopen bills only what is new.
    """
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)
    _require_move(ticket, TicketStatus.AWAITING_CONFIRMATION)

    for job in Job.objects.select_for_update(of=("self",)).filter(ticket=ticket):
        finish_visit(job, actor)

    _bill_unbilled_lines(ticket, actor)
    _update(ticket, actor, "work_finished", status=TicketStatus.AWAITING_CONFIRMATION)
    return ticket


def _bill_unbilled_lines(ticket, actor):
    """
    One invoice for what is new: a repair invoice if anything is charged,
    otherwise the zero-charge invoice covered work is owed (spec.md F19).
    """
    lines = list(ticket.work_lines.select_for_update()
                 .filter(voided_reason="", invoice__isnull=True))
    if not lines:
        return None

    gross = sum((line.charge_excl_tax + line.charge_tax for line in lines), ZERO)
    kind = InvoiceKind.REPAIR if gross > ZERO else InvoiceKind.ZERO_CHARGE
    invoice = issue_invoice(ticket.order, kind, gross, actor, ticket=ticket)
    WorkLine.objects.filter(pk__in=[line.pk for line in lines]).update(invoice=invoice)
    return invoice


@transaction.atomic
def confirm_resolution(ticket_id, data, actor):
    """The only way to Closed. A technician marking work done is not this."""
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)
    _require_move(ticket, TicketStatus.CLOSED)

    name = data.get("customer_name", "").strip()
    if not name:
        raise ValidationError({"customer_name": ["Record who confirmed it."]})

    _update(ticket, actor, "closed", reason=f"Confirmed by {name}", status=TicketStatus.CLOSED,
            confirmed_by_name=name, confirmed_at=timezone.now())
    return ticket


@transaction.atomic
def send_back(ticket_id, data, actor):
    """The customer says it is not fixed, so the work is open again."""
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)
    if ticket.status != TicketStatus.AWAITING_CONFIRMATION:
        raise ValidationError({"status": ["Only work awaiting confirmation can be sent back."]})
    return _reopen(ticket, data, actor, "sent_back")


@transaction.atomic
def reopen_ticket(ticket_id, data, actor):
    ticket = _locked_ticket(ticket_id)
    check_revision(ticket, data)
    if ticket.status != TicketStatus.CLOSED:
        raise ValidationError({"status": ["Only a closed ticket can be reopened."]})
    return _reopen(ticket, data, actor, "reopened")


def _reopen(ticket, data, actor, action):
    reason = data.get("reason", "").strip()
    if not reason:
        raise ValidationError({"reason": ["Say why the work is open again."]})

    # The previous confirmation is kept in the audit event's before values.
    _update(ticket, actor, action, reason=reason, status=TicketStatus.IN_PROGRESS,
            confirmed_by_name="", confirmed_at=None)
    return ticket


# ============================================================
# Helpers
# ============================================================

def is_office(user):
    """Anyone who works tickets rather than attending them."""
    return user.has_any_role(Role.SUPPORT, Role.OPERATIONS_MANAGER)


def _locked_ticket(ticket_id):
    ticket = ServiceTicket.objects.select_for_update().filter(pk=ticket_id).first()
    if ticket is None:
        raise NotFound()
    return ticket


def _ticket_asset(ticket, asset_id):
    asset = (TicketAsset.objects.select_related("unit", "warranty")
             .filter(pk=asset_id, ticket=ticket).first())
    if asset is None:
        raise ValidationError({"asset": ["That unit is not on this ticket."]})
    return asset


def _require_working(ticket):
    if ticket.status != TicketStatus.IN_PROGRESS:
        raise ValidationError({"status": ["Start the work first."]})


def _require_move(ticket, target):
    if target not in ALLOWED_TICKET_MOVES.get(ticket.status, []):
        raise ValidationError({"status": [
            f"A {ticket.get_status_display().lower()} ticket cannot become "
            f"{TicketStatus(target).label.lower()}."
        ]})


def _update(ticket, actor, action, *, reason="", **fields):
    before = {"status": ticket.status, "revision": ticket.revision,
              "confirmed_by_name": ticket.confirmed_by_name}
    ServiceTicket.objects.filter(pk=ticket.pk).update(
        revision=ticket.revision + 1, updated_at=timezone.now(), **fields
    )
    ticket.refresh_from_db()
    record_event(ticket, action, actor, before=before,
                 after={"status": ticket.status, "revision": ticket.revision}, reason=reason)
