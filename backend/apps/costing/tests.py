"""
F14 - what costing has to prove.

The expensive mistakes are all double counts or silent gaps: buying stock
booked as a job cost, a pay rise rewriting an old job, labour counted as
both cost and payment, a warranty repair's cost going missing, or a job
that looks profitable only because its hours were never recorded.
"""

import threading
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.api import business_date
from apps.inventory.models import PurchaseOrder, SerializedUnit, StockStatus, SupplierPaymentStatus
from apps.orders.models import Order, OrderStatus, PaymentStatus
from apps.scheduling.models import Job, JobKind, JobStatus
from apps.support.tests import PART_COST, SupportFixture

from .models import ProjectExpense, TechnicianRate, TimeEntry
from .services import costs_for_orders, outstanding_pay

User = get_user_model()
JSON = "application/json"

RATE = Decimal("400.00")
UNIT_COST = Decimal("10.00")


class CostFixture(SupportFixture):
    """A delivered order, an installation job, and a technician with a rate."""

    def setUp(self):
        super().setUp()
        self.director = User.objects.create_user("cost_dir", roles=[Role.DIRECTOR])
        TechnicianRate.objects.create(technician=self.technician, rate_per_hour=RATE,
                                      effective_from=date(2020, 1, 1), created_by=self.finance)
        self.job = self.make_job(JobKind.INSTALLATION)

    def make_job(self, kind, ticket=None):
        job = Job.objects.create(
            kind=kind, site=self.order.site, order=self.order, ticket=ticket,
            status=JobStatus.IN_PROGRESS, created_by=self.manager,
            starts_at=business_date_time(), ends_at=business_date_time(hours=2),
        )
        job.assignments.create(technician=self.technician, is_lead=True)
        return job

    def post(self, name, actor=None, **body):
        self.client.force_login(actor or self.finance)
        return self.client.post(reverse(name), body, content_type=JSON)

    def log_time(self, hours="5", work_date=None, job=None, actor=None):
        return self.post("time-entries", actor or self.technician,
                         job=(job or self.job).pk, hours=hours,
                         work_date=str(work_date or business_date()))

    def figures(self):
        order = Order.objects.select_related("quotation").get(pk=self.order.pk)
        return costs_for_orders([order])[order.pk]


def business_date_time(hours=0):
    return timezone.now() + timedelta(hours=hours)


class CostTestCase(CostFixture, TestCase):
    pass


# ============================================================
# Time and rates
# ============================================================

class TimeEntryTests(CostTestCase):
    def test_a_time_entry_accrues_at_the_technicians_rate(self):
        response = self.log_time("5")

        self.assertEqual(response.status_code, 201, response.content)
        entry = TimeEntry.objects.get()
        self.assertEqual(entry.rate_per_hour, RATE)
        self.assertEqual(entry.cost_amount, Decimal("2000.00"))
        self.assertEqual(outstanding_pay(self.technician), Decimal("2000.00"))

    def test_a_later_pay_rise_never_rewrites_a_finished_job(self):
        self.log_time("5")

        TechnicianRate.objects.create(technician=self.technician, rate_per_hour="900.00",
                                      effective_from=business_date(), created_by=self.finance)

        self.assertEqual(TimeEntry.objects.get().cost_amount, Decimal("2000.00"))

    def test_the_rate_is_the_one_in_force_on_the_day_of_the_work(self):
        TechnicianRate.objects.create(technician=self.technician, rate_per_hour="900.00",
                                      effective_from=business_date(), created_by=self.finance)

        self.log_time("1", work_date=business_date() - timedelta(days=3))

        self.assertEqual(TimeEntry.objects.get().rate_per_hour, RATE)

    def test_no_rate_is_refused_rather_than_saved_at_nothing(self):
        """An entry at zero would make the job look more profitable than it was."""
        newcomer = User.objects.create_user("cost_new", roles=[Role.TECHNICIAN])
        self.job.assignments.create(technician=newcomer)

        response = self.log_time(actor=newcomer)

        self.assertEqual(response.status_code, 400)
        self.assertIn("no cost rate", str(response.content))

    def test_a_technician_not_on_the_job_is_refused(self):
        stranger = User.objects.create_user("cost_stranger", roles=[Role.TECHNICIAN])

        self.assertEqual(self.log_time(actor=stranger).status_code, 400)

    def test_a_cancelled_job_takes_no_hours(self):
        Job.objects.filter(pk=self.job.pk).update(status=JobStatus.CANCELLED)

        self.assertEqual(self.log_time().status_code, 400)

    def test_future_hours_are_refused(self):
        self.assertEqual(
            self.log_time(work_date=business_date() + timedelta(days=1)).status_code, 400)

    def test_more_than_a_day_is_refused(self):
        self.assertEqual(self.log_time("25").status_code, 400)

    def test_a_resubmitted_day_does_not_accrue_twice(self):
        self.log_time("5")

        self.assertEqual(self.log_time("5").status_code, 400)
        self.assertEqual(outstanding_pay(self.technician), Decimal("2000.00"))

    def test_a_technician_cannot_record_someone_elses_hours(self):
        other = User.objects.create_user("cost_other", roles=[Role.TECHNICIAN])

        response = self.post("time-entries", other, job=self.job.pk, hours="1",
                             technician=self.technician.pk, work_date=str(business_date()))

        self.assertEqual(response.status_code, 403)

    def test_operations_can_record_hours_for_a_technician(self):
        response = self.post("time-entries", self.manager, job=self.job.pk, hours="1",
                             technician=self.technician.pk, work_date=str(business_date()))

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(TimeEntry.objects.get().recorded_by, self.manager)

    def test_a_rate_change_is_a_new_row(self):
        rate = TechnicianRate.objects.get()
        rate.rate_per_hour = "1.00"

        with self.assertRaises(ModelValidationError):
            rate.save()

    def test_a_reversed_entry_stops_counting_but_stays_on_the_ledger(self):
        self.log_time("5")
        entry = TimeEntry.objects.get()

        self.client.force_login(self.finance)
        response = self.client.post(reverse("time-reverse", args=[entry.pk]),
                                    {"reason": "Wrong job"}, content_type=JSON)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(outstanding_pay(self.technician), Decimal("0.00"))
        self.assertEqual(TimeEntry.objects.count(), 1)
        self.assertEqual(self.log_time("5").status_code, 201)


class RateTests(CostTestCase):
    def test_finance_sets_a_rate(self):
        response = self.post("technician-rates", technician=self.technician.pk,
                             rate_per_hour="500.00", effective_from="2030-01-01")

        self.assertEqual(response.status_code, 201, response.content)

    def test_two_rates_cannot_start_on_one_date(self):
        response = self.post("technician-rates", technician=self.technician.pk,
                             rate_per_hour="500.00", effective_from="2020-01-01")

        self.assertEqual(response.status_code, 400)


# ============================================================
# Paying technicians
# ============================================================

class TechnicianPayTests(CostTestCase):
    def pay(self, amount, **fields):
        return self.post("technician-payments", technician=self.technician.pk, amount=amount,
                         paid_on=str(business_date()), **fields)

    def test_a_payment_reduces_what_is_owed(self):
        self.log_time("5")

        self.assertEqual(self.pay("1500.00").status_code, 201)
        self.assertEqual(outstanding_pay(self.technician), Decimal("500.00"))

    def test_nobody_is_paid_more_than_has_accrued(self):
        self.log_time("5")

        response = self.pay("2000.01")

        self.assertEqual(response.status_code, 400)
        self.assertIn("2000.00", str(response.content))

    def test_paying_is_not_a_second_labour_cost(self):
        """Labour cost and labour payment are two views of the same work."""
        self.log_time("5")
        before = self.figures()["labour_cost"]

        self.pay("2000.00")

        self.assertEqual(before, Decimal("2000.00"))
        self.assertEqual(self.figures()["labour_cost"], before)

    def test_hours_already_paid_cannot_be_reversed_from_under_the_payment(self):
        self.log_time("5")
        self.pay("2000.00")
        self.client.force_login(self.finance)

        response = self.client.post(reverse("time-reverse", args=[TimeEntry.objects.get().pk]),
                                    {"reason": "Wrong job"}, content_type=JSON)

        self.assertEqual(response.status_code, 400)

    def test_a_reversed_payment_owes_again(self):
        self.log_time("5")
        payment = self.pay("2000.00").json()
        self.client.force_login(self.finance)

        self.client.post(reverse("technician-payment-reverse", args=[payment["id"]]),
                         {"reason": "Bounced"}, content_type=JSON)

        self.assertEqual(outstanding_pay(self.technician), Decimal("2000.00"))

    def test_the_summary_gives_each_technicians_balance(self):
        self.log_time("5")
        self.pay("500.00")
        self.client.force_login(self.finance)

        rows = self.client.get(reverse("technician-summary")).json()

        row = next(row for row in rows if row["technician"] == self.technician.pk)
        self.assertEqual(row["accrued"], "2000.00")
        self.assertEqual(row["paid"], "500.00")
        self.assertEqual(row["outstanding"], "1500.00")
        self.assertEqual(row["current_rate"], str(RATE))


# ============================================================
# Job cost
# ============================================================

class JobCostTests(CostTestCase):
    def test_issued_equipment_is_the_job_cost_not_the_purchase(self):
        figures = self.figures()
        units = SerializedUnit.objects.filter(order=self.order).count()

        self.assertGreater(units, 0)
        self.assertGreaterEqual(figures["equipment_cost"], units * UNIT_COST)

    def test_stock_on_the_shelf_costs_no_job_anything(self):
        before = self.figures()["equipment_cost"]

        self.stock_inverter()

        self.assertEqual(self.figures()["equipment_cost"], before)

    def test_a_return_reverses_the_allocated_cost(self):
        before = self.figures()["equipment_cost"]

        SerializedUnit.objects.filter(pk=self.inverter.pk).update(status=StockStatus.RETURNED)

        self.assertEqual(self.figures()["equipment_cost"], before - UNIT_COST)

    def test_revenue_excludes_tax(self):
        subtotal = self.order.quotation.subtotal_excl_tax

        self.assertEqual(self.figures()["net_revenue_excl_tax"], subtotal)
        self.assertLess(subtotal, self.order.gross_payable)

    def test_a_cancelled_order_earns_nothing(self):
        Order.objects.filter(pk=self.order.pk).update(status=OrderStatus.CANCELLED)

        self.assertEqual(self.figures()["net_revenue_excl_tax"], Decimal("0.00"))

    def test_a_refund_comes_off_revenue_without_its_tax(self):
        self.client.force_login(self.finance)
        self.client.post(reverse("payment-create", args=[self.order.pk]), {
            "kind": "refund", "amount": str(self.order.gross_payable), "method": "upi",
            "external_reference": "UPI-REF", "status": PaymentStatus.CLEARED,
            "paid_on": str(business_date()),
        }, content_type=JSON)

        self.assertEqual(self.figures()["net_revenue_excl_tax"], Decimal("0.00"))

    def test_cash_received_is_not_revenue(self):
        before = self.figures()["net_revenue_excl_tax"]
        self.client.force_login(self.finance)

        self.client.post(reverse("payment-create", args=[self.order.pk]), {
            "amount": "100.00", "method": "cash", "status": PaymentStatus.CLEARED,
            "paid_on": str(business_date()),
        }, content_type=JSON)

        self.assertEqual(self.figures()["net_revenue_excl_tax"], before)

    def test_operational_margin_is_revenue_less_the_three_costs(self):
        self.log_time("5")
        self.post("expenses", order=self.order.pk, description="Crane hire",
                  amount_excl_tax="750.00", incurred_on=str(business_date()))

        figures = self.figures()

        expected = (figures["net_revenue_excl_tax"] - figures["equipment_cost"]
                    - Decimal("2000.00") - Decimal("750.00"))
        self.assertEqual(figures["operational_margin"], expected)

    def test_a_reversed_expense_stops_counting(self):
        expense = self.post("expenses", order=self.order.pk, description="Crane hire",
                            amount_excl_tax="750.00", incurred_on=str(business_date())).json()
        self.client.force_login(self.finance)

        self.client.post(reverse("expense-reverse", args=[expense["id"]]),
                         {"reason": "Billed to the wrong job"}, content_type=JSON)

        self.assertEqual(self.figures()["project_expenses"], Decimal("0.00"))
        self.assertEqual(ProjectExpense.objects.count(), 1)

    def test_quoted_margin_uses_the_cost_frozen_with_the_quotation(self):
        figures = self.figures()
        lines = self.order.quotation.lines.select_related("price")
        expected = sum(line.quantity * (line.price.purchase_cost_excl_tax or 0) for line in lines)

        self.assertEqual(figures["quoted_cost_excl_tax"], Decimal(expected).quantize(Decimal("0.01")))

    def test_warranty_work_sits_beside_the_margin_not_inside_it(self):
        before = self.figures()["operational_margin"]
        ticket = self.in_progress()
        self.add_part(ticket)
        service_job = self.make_job(JobKind.SERVICE, ticket)
        self.log_time("2", job=service_job)

        figures = self.figures()

        self.assertEqual(figures["operational_margin"], before)
        self.assertEqual(figures["labour_cost"], Decimal("0.00"))
        self.assertEqual(figures["service_cost"], PART_COST + Decimal("800.00"))
        self.assertEqual(figures["lifetime_contribution"],
                         figures["operational_margin"] - figures["service_cost"])

    def test_a_replacement_unit_is_service_cost_not_equipment(self):
        spare = self.stock_inverter()
        ticket = self.in_progress()
        before = self.figures()["equipment_cost"]

        self.act(ticket, "replace", asset=self.asset_of(ticket).pk, code=spare.asset_id,
                 disposition="returned", reason="Failed")

        figures = self.figures()
        self.assertEqual(figures["equipment_cost"], before - UNIT_COST)
        self.assertEqual(figures["service_cost"], Decimal("7500.00"))

    def test_a_voided_part_costs_nothing(self):
        ticket = self.in_progress()
        self.add_part(ticket)
        line = ticket.work_lines.get()

        self.done(ticket, "void-line", line=line.pk, reason="Wrong part")

        self.assertEqual(self.figures()["service_cost"], Decimal("0.00"))

    def test_paid_repairs_add_to_lifetime_contribution(self):
        self.expire_cover()
        ticket = self.in_progress()
        self.add_part(ticket)
        self.done(ticket, "finish")

        figures = self.figures()

        self.assertEqual(figures["repair_revenue_excl_tax"], Decimal("1000.00"))
        self.assertEqual(figures["lifetime_contribution"],
                         figures["operational_margin"] + Decimal("1000.00") - PART_COST)

    def test_cost_figures_reach_the_browser_as_exact_text(self):
        """A bare Decimal renders as a float, which money must never be."""
        self.client.force_login(self.finance)

        body = self.client.get(reverse("job-cost", args=[self.order.pk])).json()

        self.assertIsInstance(body["operational_margin"], str)
        self.assertIsInstance(body["net_revenue_excl_tax"], str)

    def test_every_order_costs_a_fixed_number_of_queries(self):
        orders = list(Order.objects.select_related("quotation"))
        with CaptureQueriesContext(connection) as one:
            costs_for_orders(orders)

        with CaptureQueriesContext(connection) as repeated:
            costs_for_orders(orders * 3)

        self.assertEqual(len(one), len(repeated))


# ============================================================
# Suppliers
# ============================================================

class SupplierTests(CostTestCase):
    def setUp(self):
        super().setUp()
        self.purchase = PurchaseOrder.objects.create(supplier=self.supplier,
                                                     raised_by=self.warehouse)

    def invoice(self, amount="1000.00"):
        self.client.force_login(self.finance)
        return self.client.post(reverse("supplier-invoice", args=[self.purchase.pk]),
                                {"reference": "SUP-1", "amount": amount}, content_type=JSON)

    def pay(self, amount):
        return self.post("supplier-payments", purchase_order=self.purchase.pk, amount=amount,
                         paid_on=str(business_date()))

    def status(self):
        self.purchase.refresh_from_db()
        return self.purchase.supplier_payment_status

    def test_a_payment_needs_an_invoice_to_pay(self):
        self.assertEqual(self.pay("10.00").status_code, 400)

    def test_the_status_follows_the_money(self):
        self.invoice()

        self.pay("400.00")
        self.assertEqual(self.status(), SupplierPaymentStatus.PART_PAID)

        self.pay("600.00")
        self.assertEqual(self.status(), SupplierPaymentStatus.PAID)

    def test_a_supplier_cannot_be_overpaid(self):
        self.invoice()

        self.assertEqual(self.pay("1000.01").status_code, 400)

    def test_a_reversed_payment_reopens_the_invoice(self):
        self.invoice()
        payment = self.pay("1000.00").json()
        self.client.force_login(self.finance)

        self.client.post(reverse("supplier-payment-reverse", args=[payment["id"]]),
                         {"reason": "Bounced"}, content_type=JSON)

        self.assertEqual(self.status(), SupplierPaymentStatus.UNPAID)

    def test_an_invoice_cannot_shrink_below_what_was_paid(self):
        self.invoice()
        self.pay("800.00")

        self.assertEqual(self.invoice("500.00").status_code, 400)


# ============================================================
# Permissions
# ============================================================

class CostPermissionTests(CostTestCase):
    def urls(self):
        return [reverse("job-cost", args=[self.order.pk]), reverse("technician-summary"),
                reverse("technician-rates"), reverse("technician-payments"), reverse("expenses"),
                reverse("supplier-payments")]

    def test_cost_is_visible_to_the_roles_allowed_it(self):
        for user in (self.finance, self.director, self.manager):
            self.client.force_login(user)
            for url in self.urls():
                self.assertEqual(self.client.get(url).status_code, 200, f"{user} {url}")

    def test_cost_is_refused_to_everyone_else(self):
        for role in (Role.SALES, Role.SUPPORT, Role.WAREHOUSE, Role.TECHNICIAN):
            self.client.force_login(User.objects.create_user(f"cost_{role}", roles=[role]))
            for url in self.urls():
                self.assertEqual(self.client.get(url).status_code, 403, f"{role} {url}")

    def test_anonymous_is_refused(self):
        self.client.logout()

        self.assertEqual(self.client.get(self.urls()[0]).status_code, 403)

    def test_only_finance_moves_money(self):
        for user in (self.manager, self.director):
            response = self.post("expenses", user, order=self.order.pk, description="x",
                                 amount_excl_tax="1.00", incurred_on=str(business_date()))
            self.assertEqual(response.status_code, 403, user)

    def test_a_technician_sees_their_hours_but_not_the_rate(self):
        self.log_time("5")
        self.client.force_login(self.technician)

        rows = self.client.get(reverse("time-entries")).json()["results"]

        self.assertEqual(len(rows), 1)
        self.assertNotIn("rate_per_hour", rows[0])
        self.assertNotIn("cost_amount", rows[0])

    def test_a_technician_sees_only_their_own_hours(self):
        self.log_time("5")
        self.client.force_login(User.objects.create_user("cost_x", roles=[Role.TECHNICIAN]))

        self.assertEqual(self.client.get(reverse("time-entries")).json()["count"], 0)

    def test_the_database_refuses_a_negative_expense(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ProjectExpense.objects.create(order=self.order, description="x", amount_excl_tax="-1",
                                          incurred_on=business_date(), recorded_by=self.finance)


# ============================================================
# Concurrency, with real threads
# ============================================================

class SimultaneousPayTests(CostFixture, TransactionTestCase):
    def test_two_payments_cannot_both_take_the_same_balance(self):
        self.log_time("5")
        barrier = threading.Barrier(2)
        codes = []

        def pay():
            client = Client(raise_request_exception=False)
            client.force_login(self.finance)
            barrier.wait()
            codes.append(client.post(reverse("technician-payments"), {
                "technician": self.technician.pk, "amount": "2000.00",
                "paid_on": str(business_date()),
            }, content_type=JSON).status_code)
            connections.close_all()

        threads = [threading.Thread(target=pay) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(codes), [201, 400])
        self.assertEqual(outstanding_pay(self.technician), Decimal("0.00"))
