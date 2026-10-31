"""
F15 - the director's figures.

Every card is built from the rows its drill-down shows. Nothing is summed
separately for the headline, so a number can never disagree with the
records behind it. Spec.md F15: a number the director cannot trace is
not trusted.

No tables live here. The dashboard stores nothing and only reads what
other features recorded, so it can never become a second source of truth.

The four money figures stay distinct metrics with their own definitions,
and costs come from the same function the order screen uses (F14).
Period boundaries are Asia/Kolkata and weeks start on Monday.
"""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.db.models import F, Q, Sum
from rest_framework.exceptions import ValidationError

from apps.core.api import business_date
from apps.costing.models import ProjectExpense, SupplierPayment, TechnicianPayment, TimeEntry
from apps.costing.services import costs_for_orders, sum_by
from apps.customers.models import OPEN_STATUSES, Enquiry, SystemType
from apps.fulfilment.models import Fulfilment, FulfilmentStatus
from apps.installations.models import Decision, InstallationAcceptance
from apps.inventory.models import GoodsReceipt, MovementReason, PurchaseOrder, StockMovement
from apps.orders.models import (Allocation, InvoiceKind, Order, OrderStatus, Payment, PaymentKind,
                                PaymentStatus)
from apps.scheduling.models import ACTIVE_STATUSES, Job
from apps.support.models import ServiceTicket, TicketStatus

ZERO = Decimal("0.00")

PERIODS = ("today", "week", "month", "custom")
DEFAULT_PERIOD = "month"

COUNT = "count"
MONEY = "money"
HOURS = "hours"


# ============================================================
# Filters
# ============================================================

@dataclass(frozen=True)
class Filters:
    """start and end are inclusive business dates."""

    period: str
    start: date
    end: date
    status: str = ""
    system_type: str = ""

    @property
    def window(self):
        """Aware datetimes for timestamps. The end is exclusive."""
        zone = ZoneInfo(settings.BUSINESS_TIMEZONE)
        return (datetime.combine(self.start, time.min, tzinfo=zone),
                datetime.combine(self.end + timedelta(days=1), time.min, tzinfo=zone))

    @property
    def label(self):
        return f"{self.start:%d %b %Y} to {self.end:%d %b %Y}"

    @property
    def description(self):
        """Stamped on every export, so a file always says what it covers."""
        parts = [self.label]
        if self.status:
            parts.append(f"Project status: {OrderStatus(self.status).label}")
        if self.system_type:
            parts.append(f"System type: {SystemType(self.system_type).label}")
        return " | ".join(parts)


def filters_from(params):
    """Reads the query string, refusing anything it cannot honour by name."""
    period = params.get("period", DEFAULT_PERIOD)
    if period not in PERIODS:
        raise ValidationError({"period": ["Choose today, week, month or custom."]})

    today = business_date()
    if period == "today":
        start, end = today, today
    elif period == "week":
        start, end = today - timedelta(days=today.weekday()), today
    elif period == "month":
        start, end = today.replace(day=1), today
    else:
        start, end = _custom_range(params)

    status = params.get("status", "")
    if status and status not in OrderStatus.values:
        raise ValidationError({"status": ["No such project status."]})
    system_type = params.get("system_type", "")
    if system_type and system_type not in SystemType.values:
        raise ValidationError({"system_type": ["No such system type."]})

    return Filters(period, start, end, status, system_type)


def _custom_range(params):
    try:
        start = date.fromisoformat(params.get("from", ""))
        end = date.fromisoformat(params.get("to", ""))
    except ValueError:
        raise ValidationError({"from": ["A custom range needs from and to as YYYY-MM-DD."]})
    if end < start:
        raise ValidationError({"to": ["The range ends before it starts."]})
    return start, end


def scoped_orders(filters):
    orders = Order.objects.select_related("quotation", "customer")
    if filters.status:
        orders = orders.filter(status=filters.status)
    if filters.system_type:
        orders = orders.filter(
            quotation__quote__enquiry__requested_system_type=filters.system_type)
    return orders


def _row(reference, label, detail, url, *, on=None, amount=None):
    return {"reference": reference, "label": label, "detail": detail, "url": url,
            "date": on, "amount": amount}


def _order_row(order, detail, *, on=None, amount=None):
    return _row(order.reference, order.customer.full_name, detail, f"/orders/{order.pk}",
                on=on, amount=amount)


# ============================================================
# Money
# ============================================================

def _completed(filters):
    """Orders whose installation the customer accepted in the period."""
    start, end = filters.window
    accepted = (InstallationAcceptance.objects
                .filter(decision=Decision.ACCEPTED, decided_at__gte=start, decided_at__lt=end)
                .values("report__job__order", "decided_at"))
    when = {row["report__job__order"]: row["decided_at"] for row in accepted}
    orders = list(scoped_orders(filters).filter(pk__in=when))
    return orders, when


def _completed_figures(filters):
    orders, when = _completed(filters)
    costs = costs_for_orders(orders)
    return [(order, costs[order.pk], when[order.pk]) for order in orders]


def quoted_margin(filters):
    start, end = filters.window
    orders = list(scoped_orders(filters).filter(confirmed_at__gte=start, confirmed_at__lt=end)
                  .exclude(status=OrderStatus.CANCELLED))
    costs = costs_for_orders(orders)
    return [_order_row(order, "Confirmed", on=order.confirmed_at,
                       amount=costs[order.pk]["quoted_margin"]) for order in orders]


def operational_margin(filters):
    return [_order_row(order, "Completed", on=when, amount=figures["operational_margin"])
            for order, figures, when in _completed_figures(filters)]


def profitable_jobs(filters):
    return [row for row in operational_margin(filters) if row["amount"] >= ZERO]


def loss_making_jobs(filters):
    return [row for row in operational_margin(filters) if row["amount"] < ZERO]


def service_cost(filters):
    """Shown beside operational margin and never inside it (spec.md F15)."""
    return [_order_row(order, "Service cost to date", on=when, amount=figures["service_cost"])
            for order, figures, when in _completed_figures(filters)]


def lifetime_contribution(filters):
    return [_order_row(order, "After service and repairs", on=when,
                       amount=figures["lifetime_contribution"])
            for order, figures, when in _completed_figures(filters)]


def _cleared_money(filters):
    return (Payment.objects
            .filter(status=PaymentStatus.CLEARED, paid_on__gte=filters.start,
                    paid_on__lte=filters.end, order__in=scoped_orders(filters))
            .select_related("order__customer"))


def cash_collected(filters):
    """Cleared receipts less refunds. Never a subsidy estimate."""
    rows = []
    for payment in _cleared_money(filters):
        refund = payment.kind == PaymentKind.REFUND
        rows.append(_order_row(payment.order, "Refund" if refund else "Receipt",
                               on=payment.paid_on,
                               amount=-payment.amount if refund else payment.amount))
    return rows


def customer_advances(filters):
    allocations = (Allocation.objects
                   .filter(invoice__kind=InvoiceKind.ADVANCE,
                           payment__status=PaymentStatus.CLEARED,
                           payment__paid_on__gte=filters.start, payment__paid_on__lte=filters.end,
                           invoice__order__in=scoped_orders(filters))
                   .select_related("invoice__order__customer", "payment"))
    return [_order_row(row.invoice.order, row.invoice.reference, on=row.payment.paid_on,
                       amount=row.amount) for row in allocations]


def cash_paid(filters):
    """
    What left the business. Supplier and technician payments belong to no
    single project, so the project filters do not narrow this figure.
    """
    window = {"reversed_at__isnull": True}
    rows = [
        _row(row.purchase_order.reference, str(row.purchase_order.supplier), "Supplier payment",
             f"/purchasing/{row.purchase_order_id}", on=row.paid_on, amount=row.amount)
        for row in SupplierPayment.objects.filter(
            paid_on__gte=filters.start, paid_on__lte=filters.end, **window
        ).select_related("purchase_order__supplier")
    ]
    rows += [
        _row(row.reference or f"Pay {row.pk}", str(row.technician), "Technician payment",
             "/technician-pay", on=row.paid_on, amount=row.amount)
        for row in TechnicianPayment.objects.filter(
            paid_on__gte=filters.start, paid_on__lte=filters.end, **window
        ).select_related("technician")
    ]
    rows += [
        _row(row.order.reference, row.description, "Project expense", f"/orders/{row.order_id}",
             on=row.incurred_on, amount=row.amount_excl_tax)
        for row in ProjectExpense.objects.filter(
            incurred_on__gte=filters.start, incurred_on__lte=filters.end, **window
        ).select_related("order")
    ]
    return rows


def outstanding_balances(filters):
    """Tax-inclusive, as billed. As of now: a balance has no period."""
    orders = list(scoped_orders(filters).filter(
        status__in=[OrderStatus.DELIVERED, OrderStatus.COMPLETED]))
    ids = [order.pk for order in orders]

    money = Payment.objects.filter(order_id__in=ids, status=PaymentStatus.CLEARED)
    received = sum_by(money.filter(kind=PaymentKind.RECEIPT), "order_id", "amount")
    refunded = sum_by(money.filter(kind=PaymentKind.REFUND), "order_id", "amount")
    repairs = sum_by(Order.objects.filter(pk__in=ids, invoices__kind=InvoiceKind.REPAIR),
                     "pk", "invoices__amount")

    rows = []
    for order in orders:
        owed = (order.gross_payable + repairs.get(order.pk, ZERO)
                - received.get(order.pk, ZERO) + refunded.get(order.pk, ZERO))
        if owed > ZERO:
            rows.append(_order_row(order, "Balance due", on=order.balance_due_on, amount=owed))
    return rows


def stock_purchases(filters):
    receipts = (GoodsReceipt.objects
                .filter(received_on__gte=filters.start, received_on__lte=filters.end)
                .select_related("purchase_order__supplier"))
    ids = [receipt.pk for receipt in receipts]

    movements = StockMovement.objects.filter(reason=MovementReason.RECEIPT)
    units = sum_by(movements.filter(unit__goods_receipt__in=ids), "unit__goods_receipt",
                   "unit__acquisition_cost")
    lots = sum_by(movements.filter(lot__goods_receipt__in=ids), "lot__goods_receipt",
                  F("quantity") * F("lot__unit_cost"))

    return [_row(receipt.reference, str(receipt.purchase_order.supplier),
                 receipt.purchase_order.reference, f"/purchasing/{receipt.purchase_order_id}",
                 on=receipt.received_on,
                 amount=units.get(receipt.pk, ZERO) + lots.get(receipt.pk, ZERO))
            for receipt in receipts]


def supplier_payables(filters):
    """As of now, tax-inclusive, as the supplier billed it."""
    purchases = (PurchaseOrder.objects.filter(supplier_invoice_amount__isnull=False)
                 .select_related("supplier"))
    paid = sum_by(SupplierPayment.objects.filter(reversed_at__isnull=True),
                  "purchase_order", "amount")

    rows = []
    for purchase in purchases:
        owed = purchase.supplier_invoice_amount - paid.get(purchase.pk, ZERO)
        if owed > ZERO:
            rows.append(_row(purchase.reference, str(purchase.supplier),
                             purchase.supplier_invoice_reference, f"/purchasing/{purchase.pk}",
                             on=purchase.placed_on, amount=owed))
    return rows


def _time_entries(filters):
    entries = (TimeEntry.objects
               .filter(reversed_at__isnull=True, work_date__gte=filters.start,
                       work_date__lte=filters.end)
               .select_related("technician", "job"))
    if filters.status or filters.system_type:
        entries = entries.filter(job__order__in=scoped_orders(filters))
    return entries


def technician_hours(filters):
    return [_row(f"Job {entry.job_id}", str(entry.technician), entry.job.get_kind_display(),
                 f"/schedule/{entry.job_id}", on=entry.work_date, amount=entry.hours)
            for entry in _time_entries(filters)]


def labour_cost(filters):
    return [_row(f"Job {entry.job_id}", str(entry.technician), entry.job.get_kind_display(),
                 f"/schedule/{entry.job_id}", on=entry.work_date, amount=entry.cost_amount)
            for entry in _time_entries(filters)]


# ============================================================
# Work
# ============================================================

def _enquiries(filters):
    enquiries = Enquiry.objects.select_related("site__customer")
    if filters.system_type:
        enquiries = enquiries.filter(requested_system_type=filters.system_type)
    return enquiries


def _enquiry_row(enquiry, detail, on):
    return _row(enquiry.reference, enquiry.site.customer.full_name, detail,
                f"/enquiries?selected={enquiry.pk}", on=on)


def new_enquiries(filters):
    start, end = filters.window
    return [_enquiry_row(enquiry, enquiry.get_status_display(), enquiry.created_at)
            for enquiry in _enquiries(filters).filter(created_at__gte=start, created_at__lt=end)]


def overdue_enquiries(filters):
    """As of now, because overdue is a state and not an event."""
    overdue = _enquiries(filters).filter(next_action_due__lt=business_date(),
                                         status__in=OPEN_STATUSES)
    return [_enquiry_row(enquiry, enquiry.next_action, enquiry.next_action_due)
            for enquiry in overdue]


def installations_completed(filters):
    return [_order_row(order, "Accepted by the customer", on=when)
            for order, _figures, when in _completed_figures(filters)]


def installations_outstanding(filters):
    orders = scoped_orders(filters).filter(
        status__in=[OrderStatus.CONFIRMED, OrderStatus.DELIVERED])
    return [_order_row(order, order.get_status_display(), on=order.confirmed_at)
            for order in orders]


def blocked_work(filters):
    orders = scoped_orders(filters)
    jobs = (Job.objects.exclude(blocked_reason="")
            .filter(status__in=ACTIVE_STATUSES)
            .filter(Q(order__in=orders) | Q(order__isnull=True))
            .select_related("site__customer"))
    rows = [_row(f"Job {job.pk}", job.site.customer.full_name, job.blocked_reason,
                 f"/schedule/{job.pk}", on=job.starts_at) for job in jobs]

    short = Fulfilment.objects.filter(status=FulfilmentStatus.BLOCKED, order__in=orders)
    rows += [_row(row.order.reference, row.order.customer.full_name, row.blocked_reason,
                  f"/packing/{row.pk}", on=row.updated_at)
             for row in short.select_related("order__customer")]

    tickets = (ServiceTicket.objects.exclude(blocked_reason="")
               .exclude(status=TicketStatus.CLOSED).filter(order__in=orders)
               .select_related("customer"))
    rows += [_row(ticket.reference, ticket.customer.full_name, ticket.blocked_reason,
                  f"/tickets/{ticket.pk}", on=ticket.complaint_at) for ticket in tickets]
    return rows


def _open_tickets(filters, *, covered):
    tickets = (ServiceTicket.objects.exclude(status=TicketStatus.CLOSED)
               .filter(order__in=scoped_orders(filters))
               .select_related("customer").prefetch_related("assets"))
    return [_row(ticket.reference, ticket.customer.full_name, ticket.get_status_display(),
                 f"/tickets/{ticket.pk}", on=ticket.complaint_at)
            for ticket in tickets
            if all(asset.is_covered for asset in ticket.assets.all()) == covered]


def open_repairs_warranty(filters):
    return _open_tickets(filters, covered=True)


def open_repairs_non_warranty(filters):
    return _open_tickets(filters, covered=False)


# ============================================================
# The dashboard's layout
# ============================================================

@dataclass(frozen=True)
class Metric:
    key: str
    label: str
    caption: str
    kind: str
    rows: object


GROUPS = [
    ("Money", [
        Metric("quoted_margin", "Quoted margin", "Orders confirmed in the period", MONEY, quoted_margin),
        Metric("operational_margin", "Operational margin", "Jobs completed in the period", MONEY,
               operational_margin),
        Metric("cash_collected", "Cash collected", "Cleared receipts less refunds. Excludes subsidy",
               MONEY, cash_collected),
        Metric("cash_paid", "Cash paid", "Suppliers, technicians and project expenses", MONEY,
               cash_paid),
    ]),
    ("Jobs", [
        Metric("profitable_jobs", "Profitable jobs", "Completed in the period", COUNT, profitable_jobs),
        Metric("loss_making_jobs", "Loss-making jobs", "Completed in the period", COUNT,
               loss_making_jobs),
        Metric("service_cost", "Warranty and service cost",
               "On those jobs, outside operational margin", MONEY, service_cost),
        Metric("lifetime_contribution", "Lifetime job contribution",
               "Those jobs after service and repairs", MONEY, lifetime_contribution),
    ]),
    ("Work", [
        Metric("new_enquiries", "New enquiries", "Received in the period", COUNT, new_enquiries),
        Metric("overdue_enquiries", "Overdue enquiries", "As of today", COUNT, overdue_enquiries),
        Metric("installations_completed", "Installations completed", "Accepted in the period",
               COUNT, installations_completed),
        Metric("installations_outstanding", "Installations outstanding", "As of today", COUNT,
               installations_outstanding),
        Metric("blocked_work", "Blocked work", "As of today", COUNT, blocked_work),
        Metric("open_repairs_warranty", "Open repairs, warranty", "As of today", COUNT,
               open_repairs_warranty),
        Metric("open_repairs_non_warranty", "Open repairs, non-warranty", "As of today", COUNT,
               open_repairs_non_warranty),
    ]),
    ("Finance", [
        Metric("customer_advances", "Customer advances", "Cleared in the period", MONEY,
               customer_advances),
        Metric("outstanding_balances", "Outstanding balances", "As of today, incl. GST", MONEY,
               outstanding_balances),
        Metric("stock_purchases", "Stock purchases", "Received in the period", MONEY, stock_purchases),
        Metric("supplier_payables", "Supplier payables", "As of today, incl. GST", MONEY,
               supplier_payables),
        Metric("technician_hours", "Technician hours", "Worked in the period", HOURS,
               technician_hours),
        Metric("labour_cost", "Labour cost", "Worked in the period", MONEY, labour_cost),
    ]),
]

METRICS = {metric.key: metric for _title, metrics in GROUPS for metric in metrics}


def card(metric, filters):
    """The headline is always derived from the rows, and nothing else."""
    rows = metric.rows(filters)
    value = len(rows) if metric.kind == COUNT else sum((row["amount"] for row in rows), ZERO)
    return {"key": metric.key, "label": metric.label, "caption": metric.caption,
            "kind": metric.kind, "value": value, "records": len(rows)}


def dashboard(filters):
    jobs = sorted(operational_margin(filters), key=lambda row: row["amount"], reverse=True)
    return {
        "period": {"key": filters.period, "from": filters.start, "to": filters.end,
                   "label": filters.label},
        "groups": [{"title": title, "cards": [card(metric, filters) for metric in metrics]}
                   for title, metrics in GROUPS],
        "jobs": jobs,
    }
