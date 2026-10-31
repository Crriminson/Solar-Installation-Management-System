"""
Cost and payable operations for F14.

The double-counting rules from spec.md live in what each figure below
leaves out:

    Buying stock is not a job cost. Equipment reaches a job when it is
    issued, so only stock in an issued state is counted, and a return
    drops out by itself because its status changes.

    Collecting cash is not revenue. Revenue is the quotation's tax-free
    subtotal, less refunds. Payments never enter a margin.

    Labour cost and labour payment are one piece of work. Margin reads
    time entries and never reads technician payments.

    A subsidy estimate is never a customer payment, so none appears here.
"""

from decimal import Decimal, ROUND_HALF_UP

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import DecimalField, F, Sum
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models import Role
from apps.core.api import business_date
from apps.core.models import record_event
from apps.inventory.models import (BatchLot, PurchaseOrder, SerializedUnit, StockStatus,
                                   SupplierPaymentStatus)
from apps.orders.models import Order, OrderStatus, Payment, PaymentKind, PaymentStatus
from apps.quotations.models import QuoteLine
from apps.scheduling.models import Job, JobKind, JobStatus
from apps.support.models import WorkLine

from .models import (ProjectExpense, SupplierPayment, TechnicianPayment, TechnicianRate,
                     TimeEntry, ZERO)

User = get_user_model()

PENNY = Decimal("0.01")

# Stock in these states has left us, so its cost belongs to a job.
ISSUED_STATUSES = [StockStatus.DISPATCHED, StockStatus.DELIVERED, StockStatus.INSTALLED]

MONEY_FIELD = DecimalField(max_digits=16, decimal_places=2)


def rounded(amount):
    """INR to two places, half up."""
    return amount.quantize(PENNY, rounding=ROUND_HALF_UP)


# ============================================================
# Rates and time
# ============================================================

@transaction.atomic
def set_rate(data, actor):
    technician = _technician(data["technician"])
    if TechnicianRate.objects.filter(technician=technician,
                                     effective_from=data["effective_from"]).exists():
        raise ValidationError({"effective_from": ["A rate already starts on that date."]})

    rate = TechnicianRate.objects.create(
        technician=technician, rate_per_hour=data["rate_per_hour"],
        effective_from=data["effective_from"], created_by=actor,
    )
    record_event(rate, "rate_set", actor, after={
        "technician": technician.pk, "rate_per_hour": str(rate.rate_per_hour),
        "effective_from": str(rate.effective_from),
    })
    return rate


def rate_on(technician, work_date):
    """The rate as it stood when the work was done, not as it stands now."""
    return (TechnicianRate.objects
            .filter(technician=technician, effective_from__lte=work_date)
            .order_by("-effective_from").first())


@transaction.atomic
def record_time(data, actor):
    """
    Accrues hours on a job at the rate that applied.

    Refused when no rate exists, rather than saved at nothing: an entry
    with no rate would quietly understate that job's cost in F15 (D025).
    """
    job = Job.objects.select_for_update(of=("self",)).filter(pk=data["job"]).first()
    if job is None:
        raise ValidationError({"job": ["No job with that id."]})
    if job.status == JobStatus.CANCELLED:
        raise ValidationError({"job": ["A cancelled job has no hours."]})

    technician = _technician(data.get("technician") or actor.pk)
    if not job.assignments.filter(technician=technician).exists():
        raise ValidationError({"technician": [f"{technician} is not on this job."]})

    work_date = data["work_date"]
    if work_date > business_date():
        raise ValidationError({"work_date": ["That date is in the future."]})

    rate = rate_on(technician, work_date)
    if rate is None:
        raise ValidationError({"technician": [
            f"{technician} has no cost rate for {work_date}. Ask Finance to set one."
        ]})
    if TimeEntry.objects.filter(job=job, technician=technician, work_date=work_date,
                                reversed_at__isnull=True).exists():
        raise ValidationError({"work_date": ["Hours are already recorded for that day."]})

    hours = data["hours"]
    entry = TimeEntry.objects.create(
        job=job, technician=technician, work_date=work_date, hours=hours,
        rate_per_hour=rate.rate_per_hour, cost_amount=rounded(hours * rate.rate_per_hour),
        note=data.get("note", "").strip(), recorded_by=actor,
    )
    record_event(entry, "recorded", actor, after={
        "hours": str(hours), "cost_amount": str(entry.cost_amount),
    })
    return entry


@transaction.atomic
def reverse_time(entry_id, data, actor):
    """Corrects a mis-entry, unless the money has already been paid out."""
    entry = TimeEntry.objects.select_for_update().filter(pk=entry_id).first()
    if entry is None:
        raise NotFound()

    technician = _technician(entry.technician_id)
    if entry.cost_amount > outstanding_pay(technician):
        raise ValidationError({"entry": ["These hours have already been paid. Reverse the "
                                         "payment first."]})
    _reverse(entry, data, actor)
    return entry


# ============================================================
# Paying technicians
# ============================================================

def accrued_pay(technician):
    return TimeEntry.objects.filter(
        technician=technician, reversed_at__isnull=True,
    ).aggregate(total=Sum("cost_amount"))["total"] or ZERO


def paid_pay(technician):
    return TechnicianPayment.objects.filter(
        technician=technician, reversed_at__isnull=True,
    ).aggregate(total=Sum("amount"))["total"] or ZERO


def outstanding_pay(technician):
    return accrued_pay(technician) - paid_pay(technician)


@transaction.atomic
def pay_technician(data, actor):
    """The technician's row is locked so two payments cannot both fit."""
    technician = _technician(data["technician"])
    owed = outstanding_pay(technician)
    if data["amount"] > owed:
        raise ValidationError({"amount": [f"Only {owed} has accrued and is unpaid."]})

    payment = TechnicianPayment.objects.create(
        technician=technician, amount=data["amount"], paid_on=data["paid_on"],
        reference=data.get("reference", "").strip(), recorded_by=actor,
    )
    record_event(payment, "paid", actor, after={"amount": str(payment.amount)})
    return payment


@transaction.atomic
def reverse_technician_payment(payment_id, data, actor):
    payment = TechnicianPayment.objects.select_for_update().filter(pk=payment_id).first()
    if payment is None:
        raise NotFound()
    _reverse(payment, data, actor)
    return payment


# ============================================================
# Project expenses
# ============================================================

@transaction.atomic
def record_expense(data, actor):
    order = Order.objects.filter(pk=data["order"]).first()
    if order is None:
        raise ValidationError({"order": ["No order with that id."]})
    if order.status == OrderStatus.CANCELLED:
        raise ValidationError({"order": ["A cancelled order takes no further cost."]})
    if data["incurred_on"] > business_date():
        raise ValidationError({"incurred_on": ["That date is in the future."]})

    expense = ProjectExpense.objects.create(
        order=order, description=data["description"].strip(),
        amount_excl_tax=data["amount_excl_tax"], incurred_on=data["incurred_on"],
        recorded_by=actor,
    )
    record_event(expense, "recorded", actor, after={"amount": str(expense.amount_excl_tax)})
    return expense


@transaction.atomic
def reverse_expense(expense_id, data, actor):
    expense = ProjectExpense.objects.select_for_update().filter(pk=expense_id).first()
    if expense is None:
        raise NotFound()
    _reverse(expense, data, actor)
    return expense


# ============================================================
# Supplier invoices and payments
# ============================================================

@transaction.atomic
def record_supplier_invoice(purchase_id, data, actor):
    purchase = _locked_purchase(purchase_id)
    if data["amount"] < _supplier_paid(purchase):
        raise ValidationError({"amount": ["More than that has already been paid."]})

    PurchaseOrder.objects.filter(pk=purchase.pk).update(
        supplier_invoice_reference=data["reference"].strip(),
        supplier_invoice_amount=data["amount"],
        revision=purchase.revision + 1, updated_at=timezone.now(),
    )
    purchase.refresh_from_db()
    _settle_supplier_status(purchase)
    record_event(purchase, "supplier_invoice_recorded", actor,
                 after={"reference": data["reference"], "amount": str(data["amount"])})
    return purchase


@transaction.atomic
def pay_supplier(data, actor):
    purchase = _locked_purchase(data["purchase_order"])
    if purchase.supplier_invoice_amount is None:
        raise ValidationError({"purchase_order": ["Record the supplier's invoice first."]})

    owed = purchase.supplier_invoice_amount - _supplier_paid(purchase)
    if data["amount"] > owed:
        raise ValidationError({"amount": [f"Only {owed} is unpaid on this invoice."]})

    payment = SupplierPayment.objects.create(
        purchase_order=purchase, amount=data["amount"], paid_on=data["paid_on"],
        reference=data.get("reference", "").strip(), recorded_by=actor,
    )
    _settle_supplier_status(purchase)
    record_event(payment, "paid", actor, after={"amount": str(payment.amount)})
    return payment


@transaction.atomic
def reverse_supplier_payment(payment_id, data, actor):
    payment = SupplierPayment.objects.select_for_update().filter(pk=payment_id).first()
    if payment is None:
        raise NotFound()
    purchase = _locked_purchase(payment.purchase_order_id)
    _reverse(payment, data, actor)
    _settle_supplier_status(purchase)
    return payment


def _supplier_paid(purchase):
    return purchase.payments.filter(reversed_at__isnull=True).aggregate(
        total=Sum("amount"))["total"] or ZERO


def _settle_supplier_status(purchase):
    """The status follows the money, so it can never disagree with it."""
    paid = _supplier_paid(purchase)
    invoiced = purchase.supplier_invoice_amount
    if paid == ZERO:
        status = SupplierPaymentStatus.UNPAID
    elif invoiced is not None and paid >= invoiced:
        status = SupplierPaymentStatus.PAID
    else:
        status = SupplierPaymentStatus.PART_PAID
    PurchaseOrder.objects.filter(pk=purchase.pk).update(supplier_payment_status=status)


def _locked_purchase(purchase_id):
    purchase = PurchaseOrder.objects.select_for_update().filter(pk=purchase_id).first()
    if purchase is None:
        raise NotFound()
    return purchase


# ============================================================
# What a job cost
# ============================================================

def costs_for_orders(orders):
    """
    Every cost figure for a set of orders, in a fixed number of queries.

    One function for the order screen and the dashboard, so the two can
    never disagree, and grouped in the database because F15 asks this of
    every order in a period.
    """
    orders = list(orders)
    ids = [order.pk for order in orders]

    equipment = sum_by(
        SerializedUnit.objects.filter(order_id__in=ids, status__in=ISSUED_STATUSES,
                                      replacement_for__isnull=True),
        "order_id", "acquisition_cost",
    )
    bulk = sum_by(
        BatchLot.objects.filter(order_id__in=ids, status__in=ISSUED_STATUSES),
        "order_id", F("unit_cost") * F("quantity"),
    )
    live_time = TimeEntry.objects.filter(job__order_id__in=ids, reversed_at__isnull=True)
    labour = sum_by(live_time.exclude(job__kind=JobKind.SERVICE), "job__order_id", "cost_amount")
    hours = sum_by(live_time.exclude(job__kind=JobKind.SERVICE), "job__order_id", "hours")
    service_labour = sum_by(live_time.filter(job__kind=JobKind.SERVICE),
                                   "job__order_id", "cost_amount")
    expenses = sum_by(
        ProjectExpense.objects.filter(order_id__in=ids, reversed_at__isnull=True),
        "order_id", "amount_excl_tax",
    )
    live_lines = WorkLine.objects.filter(ticket__order_id__in=ids, voided_reason="")
    service_parts = sum_by(live_lines, "ticket__order_id", F("quantity") * F("unit_cost"))
    repair_revenue = sum_by(live_lines.exclude(invoice__isnull=True), "ticket__order_id",
                                   "charge_excl_tax")
    quoted_cost = sum_by(
        QuoteLine.objects.filter(quotation__order__in=ids), "quotation__order",
        F("quantity") * F("price__purchase_cost_excl_tax"),
    )
    refunds = _cleared_refunds(ids)

    return {order.pk: _job_figures(order, {
        "equipment": equipment.get(order.pk, ZERO) + bulk.get(order.pk, ZERO),
        "labour": labour.get(order.pk, ZERO), "hours": hours.get(order.pk, ZERO),
        "service": service_parts.get(order.pk, ZERO) + service_labour.get(order.pk, ZERO),
        "expenses": expenses.get(order.pk, ZERO), "quoted_cost": quoted_cost.get(order.pk, ZERO),
        "repair_revenue": repair_revenue.get(order.pk, ZERO),
        "refunds": refunds.get(order.pk, ZERO),
    }) for order in orders}


def sum_by(queryset, key, value):
    rows = (queryset.values(key)
            .annotate(total=Sum(value, output_field=MONEY_FIELD)).order_by())
    return {row[key]: row["total"] or ZERO for row in rows}


def _cleared_refunds(ids):
    return sum_by(
        Payment.objects.filter(order_id__in=ids, kind=PaymentKind.REFUND,
                               status=PaymentStatus.CLEARED),
        "order_id", "amount",
    )


def _job_figures(order, totals):
    """
    Revenue excludes tax, and refunds come off at the order's own tax ratio,
    because a refund is paid tax-inclusive. Operational margin is the
    spec's definition; later service is shown beside it, not inside it.
    """
    quotation = order.quotation
    subtotal = quotation.subtotal_excl_tax
    gross = quotation.gross_payable_incl_tax
    cancelled = order.status == OrderStatus.CANCELLED

    refunded = rounded(totals["refunds"] * subtotal / gross) if gross else ZERO
    revenue = ZERO if cancelled else subtotal - refunded

    equipment = rounded(totals["equipment"])
    service = rounded(totals["service"])
    margin = revenue - equipment - totals["labour"] - totals["expenses"]
    quoted_cost = rounded(totals["quoted_cost"])

    return {
        "order": order.pk, "reference": order.reference, "status": order.status,
        "net_revenue_excl_tax": revenue, "quoted_cost_excl_tax": quoted_cost,
        "quoted_margin": subtotal - quoted_cost, "equipment_cost": equipment,
        "labour_cost": totals["labour"], "labour_hours": totals["hours"],
        "project_expenses": totals["expenses"], "operational_margin": margin,
        "service_cost": service, "repair_revenue_excl_tax": totals["repair_revenue"],
        "lifetime_contribution": margin + totals["repair_revenue"] - service,
    }


def technician_summaries():
    """Hours, accrual and balance per technician, without a query per person."""
    live = TimeEntry.objects.filter(reversed_at__isnull=True)
    accrued = sum_by(live, "technician", "cost_amount")
    hours = sum_by(live, "technician", "hours")
    paid = sum_by(TechnicianPayment.objects.filter(reversed_at__isnull=True),
                         "technician", "amount")

    rates = {}
    for rate in TechnicianRate.objects.filter(effective_from__lte=business_date()).order_by(
            "effective_from", "id"):
        rates[rate.technician_id] = rate.rate_per_hour

    staff = [user for user in User.objects.filter(is_active_staff=True).order_by("username")
             if Role.TECHNICIAN in user.roles or user.pk in accrued]
    return [{
        "technician": user.pk, "name": str(user), "current_rate": rates.get(user.pk),
        "hours": hours.get(user.pk, ZERO), "accrued": accrued.get(user.pk, ZERO),
        "paid": paid.get(user.pk, ZERO),
        "outstanding": accrued.get(user.pk, ZERO) - paid.get(user.pk, ZERO),
    } for user in staff]


# ============================================================
# Helpers
# ============================================================

def _technician(user_id):
    """Locked, because a payable is a balance two people could race over."""
    technician = User.objects.select_for_update().filter(pk=user_id).first()
    if technician is None:
        raise ValidationError({"technician": ["No staff member with that id."]})
    return technician


def _reverse(entry, data, actor):
    reason = data.get("reason", "").strip()
    if not reason:
        raise ValidationError({"reason": ["Say why this is being reversed."]})
    if entry.is_reversed:
        raise ValidationError({"reversed": ["This has already been reversed."]})

    type(entry).objects.filter(pk=entry.pk).update(
        reversed_reason=reason, reversed_at=timezone.now()
    )
    entry.refresh_from_db()
    record_event(entry, "reversed", actor, reason=reason)
