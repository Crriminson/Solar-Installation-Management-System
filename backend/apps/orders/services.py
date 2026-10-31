"""
Locked, audited money operations for F07.

Every function here runs inside one transaction with the order row
locked, because two people recording a payment on the same order at the
same moment must not both read the same balance and both decide the
advance has cleared.

The Python checks below give a readable error. The check constraints in
models.py are the real guarantee: they hold even if a future caller
forgets to come through this module.
"""

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.api import business_date, check_revision
from apps.core.models import record_event
from apps.quotations.models import QuoteRevision, QuoteStatus

from .models import (Allocation, Invoice, InvoiceKind, Order, OrderStatus, Payment,
                     PaymentKind, PaymentPlan, PaymentStatus, ZERO)


# ============================================================
# Order confirmation
# ============================================================

@transaction.atomic
def confirm_order(quotation_id, actor):
    """
    Turns an accepted quotation into an order.

    Confirming twice is safe: the one-to-one means the second call finds
    the existing order and returns it rather than billing the customer
    for a second job.
    """
    get_user_model().objects.select_for_update().get(pk=actor.pk)

    quotation = (QuoteRevision.objects
                 .select_for_update()
                 .select_related("quote")
                 .filter(pk=quotation_id)
                 .first())
    if quotation is None:
        raise NotFound()

    existing = Order.objects.filter(quotation=quotation).first()
    if existing is not None:
        return existing

    if quotation.status != QuoteStatus.ACCEPTED:
        raise ValidationError(
            {"status": ["Only an accepted quotation becomes an order."]}
        )

    terms = quotation.terms or {}
    plan = terms.get("plan", PaymentPlan.ADVANCE)
    gross = quotation.gross_payable_incl_tax
    advance = (Decimal(terms["advance_amount_incl_tax"])
               if plan == PaymentPlan.ADVANCE else gross)

    order = Order.objects.create(
        quotation=quotation,
        customer=quotation.customer,
        site=quotation.site,
        payment_plan=plan,
        gross_payable=gross,
        advance_payable=advance,
        confirmed_by=actor,
        confirmed_at=timezone.now(),
    )
    record_event(order, "confirmed", actor,
                 after={"reference": order.reference, "gross_payable": str(gross)})

    # The customer is asked for the first money straight away, so nobody
    # has to remember to raise it.
    first_kind = InvoiceKind.ADVANCE if plan == PaymentPlan.ADVANCE else InvoiceKind.FULL
    issue_invoice(order, first_kind, advance, actor)
    return order


@transaction.atomic
def cancel_order(order_id, data, actor):
    """Cancels an order. Money already taken is returned as a refund, not erased."""
    order = _locked_order(order_id)
    check_revision(order, data)

    if order.status == OrderStatus.CANCELLED:
        raise ValidationError({"status": ["This order is already cancelled."]})
    if not data.get("reason", "").strip():
        raise ValidationError({"reason": ["Say why the order is being cancelled."]})

    _update_order(order, actor, "cancelled", reason=data["reason"],
                  status=OrderStatus.CANCELLED, cancelled_reason=data["reason"].strip())
    return order


# ============================================================
# Invoices
# ============================================================

def issue_invoice(order, kind, amount, actor):
    """
    Raises one invoice against the order.

    The unique constraint on (order, kind) is what stops a deposit being
    billed twice; this check only turns that into a readable message.
    """
    if amount <= ZERO:
        raise ValidationError({"amount": ["An invoice must be for more than nothing."]})

    if Invoice.objects.filter(order=order, kind=kind).exists():
        raise ValidationError(
            {"kind": [f"This order already has a {kind} invoice."]}
        )

    invoice = Invoice.objects.create(
        order=order, kind=kind, amount=amount, issued_by=actor, issued_at=timezone.now()
    )
    record_event(invoice, "issued", actor,
                 after={"reference": invoice.reference, "amount": str(amount)})
    return invoice


@transaction.atomic
def issue_balance_invoice(order_id, actor):
    """
    Bills the remainder. Due on delivery completion, per D024.

    Installation acceptance is not a payment gate, so this does not wait
    for the system to be signed off.
    """
    order = _locked_order(order_id)

    if order.payment_plan != PaymentPlan.ADVANCE:
        raise ValidationError({"order": ["A full-payment order has no balance invoice."]})
    if order.status == OrderStatus.CANCELLED:
        raise ValidationError({"order": ["This order is cancelled."]})

    balance = order.gross_payable - order.advance_payable
    invoice = issue_invoice(order, InvoiceKind.BALANCE, balance, actor)

    if order.balance_due_on is None:
        _update_order(order, actor, "balance_due_set", balance_due_on=business_date())
    return invoice


# ============================================================
# Payments
# ============================================================

@transaction.atomic
def record_payment(order_id, data, actor):
    """
    Records money that moved. Nothing is settled until it clears.

    The partial unique index on (method, external_reference) is what
    stops the same bank reference being banked twice.
    """
    order = _locked_order(order_id)

    if order.status == OrderStatus.CANCELLED and data["kind"] == PaymentKind.RECEIPT:
        raise ValidationError({"order": ["A cancelled order takes no further receipts."]})
    if data["paid_on"] > business_date():
        raise ValidationError({"paid_on": ["Money cannot have moved in the future."]})

    reference = data.get("external_reference", "").strip()
    if reference and Payment.objects.filter(
            method=data["method"], external_reference=reference).exists():
        raise ValidationError(
            {"external_reference": ["This reference has already been recorded."]}
        )

    payment = Payment.objects.create(
        order=order,
        kind=data["kind"],
        amount=data["amount"],
        method=data["method"],
        external_reference=reference,
        status=data.get("status", PaymentStatus.PENDING),
        paid_on=data["paid_on"],
        recorded_by=actor,
    )
    record_event(payment, "recorded", actor,
                 after={"amount": str(payment.amount), "status": payment.status})

    if payment.status == PaymentStatus.CLEARED:
        auto_allocate(payment, actor)
    return payment


def auto_allocate(payment, actor):
    """
    Points a cleared receipt at the oldest unsettled invoice.

    The common case is one advance against one advance invoice, and
    making somebody press a second button for that teaches them to skip
    allocation entirely. Finance can still reallocate by hand where a
    customer has paid against a specific invoice.

    Takes the same caps as a manual allocation, so this can never
    overpay an invoice or over-allocate a payment.
    """
    if payment.kind != PaymentKind.RECEIPT:
        return

    invoices = (Invoice.objects.select_for_update()
                .filter(order_id=payment.order_id)
                .exclude(paid_amount=models.F("amount"))
                .order_by("id"))

    for invoice in invoices:
        spare = payment.amount - payment.allocated_amount
        owing = invoice.amount - invoice.paid_amount
        amount = min(spare, owing)
        if amount <= ZERO:
            continue

        Allocation.objects.create(payment=payment, invoice=invoice, amount=amount)
        Invoice.objects.filter(pk=invoice.pk).update(
            paid_amount=invoice.paid_amount + amount)
        Payment.objects.filter(pk=payment.pk).update(
            allocated_amount=payment.allocated_amount + amount)
        payment.refresh_from_db()
        record_event(payment, "auto_allocated", actor,
                     after={"invoice": invoice.reference, "amount": str(amount)})

        if payment.allocated_amount >= payment.amount:
            break


@transaction.atomic
def clear_payment(payment_id, data, actor):
    """Confirms the money actually arrived. Only now does it count."""
    payment = _locked_payment(payment_id)
    check_revision(payment, data)

    if payment.status != PaymentStatus.PENDING:
        raise ValidationError(
            {"status": [f"Only a pending payment can be cleared; this one is {payment.status}."]}
        )

    _update_payment(payment, actor, "cleared", status=PaymentStatus.CLEARED)
    auto_allocate(payment, actor)
    return payment


@transaction.atomic
def reverse_payment(payment_id, data, actor):
    """
    Undoes a mis-entry. The row stays and its allocations are released.

    This is for a payment that was recorded wrongly. Money genuinely
    going back to the customer is a refund, which is its own payment.
    """
    payment = _locked_payment(payment_id)
    check_revision(payment, data)

    if payment.status == PaymentStatus.REVERSED:
        raise ValidationError({"status": ["This payment is already reversed."]})
    if not data.get("reason", "").strip():
        raise ValidationError({"reason": ["Say why the payment is being reversed."]})

    for allocation in payment.allocations.select_related("invoice"):
        invoice = Invoice.objects.select_for_update().get(pk=allocation.invoice_id)
        Invoice.objects.filter(pk=invoice.pk).update(
            paid_amount=invoice.paid_amount - allocation.amount
        )

    payment.allocations.all().delete()
    _update_payment(payment, actor, "reversed", reason=data["reason"],
                    status=PaymentStatus.REVERSED,
                    allocated_amount=ZERO,
                    reversed_reason=data["reason"].strip())
    return payment


@transaction.atomic
def allocate_payment(payment_id, data, actor):
    """
    Points part of a payment at an invoice.

    Both sides are capped: a payment cannot settle more than it is worth,
    and an invoice cannot be paid beyond its amount. Both caps are check
    constraints, so a concurrent allocation cannot slip past them.
    """
    payment = _locked_payment(payment_id)
    invoice = Invoice.objects.select_for_update().filter(pk=data["invoice"]).first()

    if invoice is None or invoice.order_id != payment.order_id:
        raise ValidationError({"invoice": ["That invoice is not on this order."]})
    if payment.status != PaymentStatus.CLEARED:
        raise ValidationError({"payment": ["Only a cleared payment can be allocated."]})
    if payment.kind != PaymentKind.RECEIPT:
        raise ValidationError({"payment": ["A refund is not allocated against an invoice."]})

    amount = data["amount"]
    if amount > payment.unallocated:
        raise ValidationError(
            {"amount": [f"Only {payment.unallocated} of this payment is unallocated."]}
        )
    if amount > invoice.amount - invoice.paid_amount:
        raise ValidationError(
            {"amount": [f"Only {invoice.amount - invoice.paid_amount} is outstanding on "
                        f"{invoice.reference}."]}
        )

    allocation = Allocation.objects.create(payment=payment, invoice=invoice, amount=amount)
    Invoice.objects.filter(pk=invoice.pk).update(paid_amount=invoice.paid_amount + amount)
    Payment.objects.filter(pk=payment.pk).update(
        allocated_amount=payment.allocated_amount + amount
    )
    record_event(allocation, "allocated", actor,
                 after={"invoice": invoice.reference, "amount": str(amount)})

    payment.refresh_from_db()
    return payment


# ============================================================
# Helpers
# ============================================================

def _locked_order(order_id):
    order = Order.objects.select_for_update().filter(pk=order_id).first()
    if order is None:
        raise NotFound()
    return order


def _locked_payment(payment_id):
    payment = (Payment.objects.select_for_update()
               .select_related("order")
               .filter(pk=payment_id)
               .first())
    if payment is None:
        raise NotFound()
    # Lock the order too, so a balance read elsewhere cannot race this.
    Order.objects.select_for_update().get(pk=payment.order_id)
    return payment


def _update_order(order, actor, action, *, reason="", **fields):
    before = {"status": order.status, "revision": order.revision}
    Order.objects.filter(pk=order.pk).update(
        revision=order.revision + 1, updated_at=timezone.now(), **fields
    )
    order.refresh_from_db()
    record_event(order, action, actor, before=before,
                 after={"status": order.status, "revision": order.revision}, reason=reason)


def _update_payment(payment, actor, action, *, reason="", **fields):
    before = {"status": payment.status, "revision": payment.revision}
    Payment.objects.filter(pk=payment.pk).update(revision=payment.revision + 1, **fields)
    payment.refresh_from_db()
    record_event(payment, action, actor, before=before,
                 after={"status": payment.status, "revision": payment.revision}, reason=reason)
