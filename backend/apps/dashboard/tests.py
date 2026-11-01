"""
F15 - what the dashboard has to prove.

The director acts on these numbers, so the expensive mistakes are a
figure that cannot be traced, a period boundary in the wrong timezone,
two money figures quietly merged, and a financial view reaching someone
it should not.
"""

from datetime import date, datetime, timedelta, timezone as utc
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.test import SimpleTestCase, TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Role
from apps.core.api import business_date
from apps.costing.models import TimeEntry
from apps.costing.services import costs_for_orders
from apps.costing.tests import CostFixture
from apps.customers.models import Enquiry
from apps.installations.models import InstallationAcceptance, InstallationReport
from apps.orders.models import Order, OrderStatus, PaymentStatus
from apps.quotations.test_acceptance import signature_file
from apps.scheduling.models import JobKind, JobStatus

from .exports import generated_stamp, indian_number, metric_csv, safe_cell
from .metrics import GROUPS, METRICS, Filters, card, dashboard, filters_from, operational_margin

User = get_user_model()
JSON = "application/json"


def filters(**changes):
    today = business_date()
    values = {"period": "custom", "start": today - timedelta(days=30), "end": today}
    return Filters(**{**values, **changes})


class DashboardFixture(CostFixture):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.director)

    def complete_the_job(self, decided_at=None):
        """Accepts the installation, which is what completes an order."""
        report = InstallationReport.objects.create(
            job=self.job, status="accepted", created_by=self.technician)
        InstallationAcceptance.objects.create(
            report=report, decision="accepted", customer_name="Ramesh Gupta",
            signature=signature_file(), document_revision=1, document_content_hash="x",
            witnessed_by=self.technician, decided_at=decided_at or timezone.now(),
        )
        Order.objects.filter(pk=self.order.pk).update(status=OrderStatus.COMPLETED)

    def get(self, name="dashboard", *args, **params):
        response = self.client.get(reverse(name, args=args), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response

    def card_value(self, key, **changes):
        return card(METRICS[key], filters(**changes))["value"]


class DashboardTestCase(DashboardFixture, TestCase):
    pass


# ============================================================
# Periods
# ============================================================

class PeriodTests(SimpleTestCase):
    @patch("apps.dashboard.metrics.business_date", return_value=date(2026, 10, 28))
    def test_a_week_starts_on_monday(self, _today):
        """28 October 2026 is a Wednesday."""
        chosen = filters_from({"period": "week"})

        self.assertEqual(chosen.start, date(2026, 10, 26))
        self.assertEqual(chosen.start.weekday(), 0)
        self.assertEqual(chosen.end, date(2026, 10, 28))

    @patch("apps.dashboard.metrics.business_date", return_value=date(2026, 10, 26))
    def test_on_a_monday_the_week_is_that_day(self, _today):
        self.assertEqual(filters_from({"period": "week"}).start, date(2026, 10, 26))

    @patch("apps.dashboard.metrics.business_date", return_value=date(2026, 10, 28))
    def test_a_month_starts_on_the_first(self, _today):
        self.assertEqual(filters_from({"period": "month"}).start, date(2026, 10, 1))

    @patch("apps.dashboard.metrics.business_date", return_value=date(2026, 10, 28))
    def test_month_is_the_default(self, _today):
        self.assertEqual(filters_from({}).period, "month")

    def test_a_custom_range_is_honoured(self):
        chosen = filters_from({"period": "custom", "from": "2026-01-01", "to": "2026-03-31"})

        self.assertEqual((chosen.start, chosen.end), (date(2026, 1, 1), date(2026, 3, 31)))

    def test_bad_input_is_refused_by_name(self):
        for params in [{"period": "decade"}, {"period": "custom"},
                       {"period": "custom", "from": "x", "to": "y"},
                       {"period": "custom", "from": "2026-02-01", "to": "2026-01-01"},
                       {"status": "nonsense"}, {"system_type": "nonsense"}]:
            with self.assertRaises(ValidationError, msg=params):
                filters_from(params)

    def test_a_day_runs_midnight_to_midnight_in_india(self):
        start, end = filters(start=date(2026, 3, 1), end=date(2026, 3, 1)).window

        self.assertEqual(start.astimezone(utc.utc), datetime(2026, 2, 28, 18, 30, tzinfo=utc.utc))
        self.assertEqual(end.astimezone(utc.utc), datetime(2026, 3, 1, 18, 30, tzinfo=utc.utc))


class BoundaryTests(DashboardTestCase):
    def test_an_event_just_after_midnight_in_india_counts_on_that_day(self):
        """18:45 UTC on 28 Feb is 00:15 on 1 March in Asia/Kolkata."""
        enquiry = Enquiry.objects.get()
        Enquiry.objects.filter(pk=enquiry.pk).update(
            created_at=datetime(2026, 2, 28, 18, 45, tzinfo=utc.utc))

        march = self.card_value("new_enquiries", start=date(2026, 3, 1), end=date(2026, 3, 1))
        february = self.card_value("new_enquiries", start=date(2026, 2, 28), end=date(2026, 2, 28))

        self.assertEqual((march, february), (1, 0))


# ============================================================
# The figures
# ============================================================

class TraceabilityTests(DashboardTestCase):
    def test_a_long_drill_down_comes_a_page_at_a_time_with_the_full_count(self):
        """The tile counts every row; the screen pages through them."""
        site = Enquiry.objects.get().site
        for _ in range(30):
            Enquiry.objects.create(site=site, source="phone")
        chosen = {"period": "custom", "from": "2020-01-01", "to": str(business_date())}
        tile = card(METRICS["new_enquiries"], filters(start=date(2020, 1, 1)))["value"]

        first = self.get("dashboard-metric", "new_enquiries", **chosen).json()
        self.assertEqual(first["count"], tile)
        self.assertEqual(len(first["rows"]), settings.DEFAULT_PAGE_SIZE)

        rows = list(first["rows"])
        pages = -(-tile // settings.DEFAULT_PAGE_SIZE)
        for page in range(2, pages + 1):
            rows += self.get("dashboard-metric", "new_enquiries", page=page, **chosen).json()["rows"]
        self.assertEqual(len(rows), tile)
        self.assertEqual(len({row["reference"] for row in rows}), tile)

    def test_every_figure_can_be_opened(self):
        self.complete_the_job()

        for key in METRICS:
            body = self.get("dashboard-metric", key, period="custom", **{
                "from": "2020-01-01", "to": str(business_date())}).json()
            self.assertEqual(body["key"], key)
            self.assertIn("rows", body)

    def test_every_headline_is_the_sum_of_its_rows(self):
        """The rule the whole app rests on, checked figure by figure."""
        self.complete_the_job()
        self.log_time("5")

        chosen = filters(start=date(2020, 1, 1))
        for metric in METRICS.values():
            figure = card(metric, chosen)
            rows = metric.rows(chosen)
            expected = (len(rows) if metric.kind == "count"
                        else sum((row["amount"] for row in rows), Decimal("0.00")))
            self.assertEqual(figure["value"], expected, metric.key)

    def test_every_row_says_what_it_is_and_where_it_lives(self):
        self.complete_the_job()

        chosen = filters(start=date(2020, 1, 1))
        for metric in METRICS.values():
            for row in metric.rows(chosen):
                self.assertTrue(row["reference"], metric.key)
                self.assertTrue(row["url"].startswith("/"), metric.key)

    def test_an_unknown_figure_is_a_404(self):
        self.assertEqual(self.client.get(
            reverse("dashboard-metric", args=["nonsense"])).status_code, 404)
        self.assertEqual(self.client.get(
            reverse("dashboard-csv", args=["nonsense"])).status_code, 404)


class MoneyTests(DashboardTestCase):
    def test_the_four_money_figures_stay_separate(self):
        cards = self.get().json()["groups"][0]["cards"]

        self.assertEqual([row["key"] for row in cards],
                         ["quoted_margin", "operational_margin", "cash_collected", "cash_paid"])
        self.assertTrue(all(row["caption"] for row in cards))

    def test_nothing_is_ever_labelled_profit_as_a_money_figure(self):
        labels = [metric.label for metric in METRICS.values()]

        self.assertNotIn("Profit", labels)
        self.assertIn("Operational margin", labels)

    def test_operational_margin_counts_only_completed_jobs(self):
        self.assertEqual(self.card_value("operational_margin"), Decimal("0.00"))

        self.complete_the_job()

        self.assertNotEqual(self.card_value("operational_margin"), Decimal("0.00"))

    def test_quoted_margin_excludes_a_cancelled_order(self):
        self.assertNotEqual(self.card_value("quoted_margin"), Decimal("0.00"))

        Order.objects.filter(pk=self.order.pk).update(status=OrderStatus.CANCELLED)

        self.assertEqual(self.card_value("quoted_margin"), Decimal("0.00"))

    def test_cash_collected_counts_cleared_money_only(self):
        self.assertEqual(self.card_value("cash_collected"), self.order.advance_payable)

        self.client.force_login(self.finance)
        self.client.post(reverse("payment-create", args=[self.order.pk]), {
            "amount": "500.00", "method": "cash", "status": PaymentStatus.PENDING,
            "paid_on": str(business_date()),
        }, content_type=JSON)

        self.assertEqual(self.card_value("cash_collected"), self.order.advance_payable)

    def test_a_refund_comes_off_cash_collected(self):
        self.client.force_login(self.finance)
        self.client.post(reverse("payment-create", args=[self.order.pk]), {
            "kind": "refund", "amount": "100.00", "method": "upi",
            "external_reference": "UPI-BACK", "status": PaymentStatus.CLEARED,
            "paid_on": str(business_date()),
        }, content_type=JSON)

        self.assertEqual(self.card_value("cash_collected"),
                         self.order.advance_payable - Decimal("100.00"))

    def test_cash_paid_adds_suppliers_technicians_and_expenses(self):
        self.log_time("5")
        self.post("technician-payments", technician=self.technician.pk, amount="1000.00",
                  paid_on=str(business_date()))
        self.post("expenses", order=self.order.pk, description="Crane", amount_excl_tax="250.00",
                  incurred_on=str(business_date()))

        self.assertEqual(self.card_value("cash_paid"), Decimal("1250.00"))

    def test_accrued_hours_are_not_cash_paid(self):
        self.log_time("5")

        self.assertEqual(self.card_value("cash_paid"), Decimal("0.00"))
        self.assertEqual(self.card_value("labour_cost"), Decimal("2000.00"))
        self.assertEqual(self.card_value("technician_hours"), Decimal("5.00"))

    def test_outstanding_balances_match_the_orders_own_figure(self):
        self.assertEqual(self.card_value("outstanding_balances"), self.order.outstanding())

    def test_outstanding_balances_include_an_unpaid_repair(self):
        self.expire_cover()
        ticket = self.in_progress()
        self.add_part(ticket)
        self.done(ticket, "finish")

        self.assertEqual(self.card_value("outstanding_balances"), self.order.outstanding())

    def test_stock_purchases_value_what_was_received(self):
        self.assertGreater(self.card_value("stock_purchases"), Decimal("0.00"))

    def test_reversed_time_stops_counting(self):
        self.log_time("5")
        TimeEntry.objects.update(reversed_at=timezone.now(), reversed_reason="Mistake")

        self.assertEqual(self.card_value("technician_hours"), Decimal("0.00"))


class JobTests(DashboardTestCase):
    def test_a_completed_job_is_either_profitable_or_loss_making(self):
        self.complete_the_job()

        self.assertEqual(self.card_value("profitable_jobs") + self.card_value("loss_making_jobs"), 1)

    def test_a_job_whose_costs_exceed_revenue_is_loss_making(self):
        self.complete_the_job()
        self.post("expenses", order=self.order.pk, description="Crane", amount_excl_tax="9999999.00",
                  incurred_on=str(business_date()))

        self.assertEqual(self.card_value("loss_making_jobs"), 1)
        self.assertEqual(self.card_value("profitable_jobs"), 0)

    def test_jobs_are_ranked_by_margin(self):
        self.complete_the_job()

        jobs = self.get().json()["jobs"]

        self.assertEqual([row["reference"] for row in jobs], [self.order.reference])

    def test_warranty_cost_is_shown_beside_the_margin_not_inside_it(self):
        self.complete_the_job()
        before = self.card_value("operational_margin")
        ticket = self.in_progress()
        self.add_part(ticket)

        self.assertEqual(self.card_value("operational_margin"), before)
        self.assertGreater(self.card_value("service_cost"), Decimal("0.00"))
        self.assertLess(self.card_value("lifetime_contribution"), before)


class WorkTests(DashboardTestCase):
    def test_a_delivered_order_is_outstanding_until_accepted(self):
        self.assertEqual(self.card_value("installations_outstanding"), 1)

        self.complete_the_job()

        self.assertEqual(self.card_value("installations_outstanding"), 0)
        self.assertEqual(self.card_value("installations_completed"), 1)

    def test_blocked_work_finds_blocked_jobs(self):
        self.client.force_login(self.manager)
        self.client.post(reverse("job-action", args=[self.job.pk, "block"]), {
            "revision": self.job.revision, "reason": "Rain", "owner": self.manager.pk,
        }, content_type=JSON)

        rows = METRICS["blocked_work"].rows(filters())

        self.assertEqual([row["reference"] for row in rows], [f"Job {self.job.pk}"])

    def test_blocked_work_finds_blocked_tickets(self):
        ticket = self.raise_ticket()
        self.done(ticket, "block", reason="Waiting on a part", owner=self.manager.pk)

        self.assertEqual(self.card_value("blocked_work"), 1)

    def test_a_finished_job_is_not_still_blocked(self):
        self.job.blocked_reason = "Rain"
        self.job.blocked_owner = self.manager
        self.job.status = JobStatus.COMPLETED
        self.job.save()

        self.assertEqual(self.card_value("blocked_work"), 0)

    def test_repairs_split_by_warranty(self):
        self.raise_ticket()
        self.expire_cover()
        self.raise_ticket()

        self.assertEqual(self.card_value("open_repairs_warranty"), 1)
        self.assertEqual(self.card_value("open_repairs_non_warranty"), 1)

    def test_a_closed_repair_is_not_open(self):
        ticket = self.in_progress()
        self.done(ticket, "finish")
        self.done(ticket, "confirm", customer_name="Ramesh Gupta")

        self.assertEqual(self.card_value("open_repairs_warranty"), 0)

    def test_an_overdue_enquiry_counts(self):
        Enquiry.objects.update(next_action_due=business_date() - timedelta(days=1),
                               status="contacting")

        self.assertEqual(self.card_value("overdue_enquiries"), 1)


class FilterTests(DashboardTestCase):
    def test_the_project_status_filter_narrows_orders(self):
        self.assertEqual(self.card_value("installations_outstanding", status="cancelled"), 0)
        self.assertEqual(self.card_value("installations_outstanding", status="delivered"), 1)

    def test_the_system_type_filter_narrows_orders(self):
        requested = self.order.quotation.quote.enquiry.requested_system_type
        other = "off_grid" if requested != "off_grid" else "on_grid"

        self.assertEqual(self.card_value("installations_outstanding", system_type=requested), 1)
        self.assertEqual(self.card_value("installations_outstanding", system_type=other), 0)

    def test_a_period_with_nothing_in_it_is_zero_not_an_error(self):
        body = self.get(period="custom", **{"from": "2001-01-01", "to": "2001-01-31"}).json()

        self.assertEqual(body["groups"][0]["cards"][0]["value"], "0.00")
        self.assertEqual(body["jobs"], [])

    def test_money_reaches_the_browser_as_exact_text(self):
        """A bare Decimal renders as a float, which money must never be."""
        self.complete_the_job()
        chosen = {"period": "custom", "from": "2020-01-01", "to": str(business_date())}

        body = self.get(**chosen).json()
        rows = self.get("dashboard-metric", "cash_collected", **chosen).json()["rows"]

        self.assertIsInstance(body["groups"][0]["cards"][0]["value"], str)
        self.assertIsInstance(body["jobs"][0]["amount"], str)
        self.assertIsInstance(rows[0]["amount"], str)

    def test_the_period_is_stated_in_the_response(self):
        body = self.get(period="custom", **{"from": "2026-01-01", "to": "2026-01-31"}).json()

        self.assertEqual(body["period"]["label"], "01 Jan 2026 to 31 Jan 2026")


# ============================================================
# Exports
# ============================================================

class ExportTests(DashboardTestCase):
    def test_a_csv_stamps_its_period_and_filters(self):
        text = self.get("dashboard-csv", "cash_collected", period="custom", status="delivered", **{
            "from": "2020-01-01", "to": str(business_date())}).content.decode()

        self.assertIn("Cash collected", text)
        self.assertIn("01 Jan 2020", text)
        self.assertIn("Project status: Delivered", text)
        self.assertIn(self.order.reference, text)

    def test_the_csv_holds_the_same_rows_as_the_screen(self):
        text = metric_csv(METRICS["cash_collected"], filters())

        rows = [line for line in text.splitlines() if self.order.reference in line]
        self.assertEqual(len(rows), len(METRICS["cash_collected"].rows(filters())))

    def test_a_customer_name_cannot_become_a_spreadsheet_formula(self):
        """The name came from a public form."""
        for hostile in ["=HYPERLINK(1)", "+1", "-1", "@SUM(1)"]:
            self.assertEqual(safe_cell(hostile), f"'{hostile}")

    def test_ordinary_values_pass_through_unchanged(self):
        self.assertEqual(safe_cell("Ramesh Gupta"), "Ramesh Gupta")
        self.assertEqual(safe_cell(Decimal("-5.00")), "-5.00")
        self.assertEqual(safe_cell(None), "")

    def test_a_hostile_name_is_neutralised_in_a_real_export(self):
        self.order.customer.__class__.objects.filter(pk=self.order.customer_id).update(
            full_name="=cmd|calc")

        text = metric_csv(METRICS["cash_collected"], filters())

        self.assertIn("'=cmd|calc", text)

    def test_a_csv_date_is_the_indian_date(self):
        """18:45 UTC on 28 Feb is 00:15 on 1 March in Asia/Kolkata."""
        moment = datetime(2026, 2, 28, 18, 45, tzinfo=utc.utc)

        self.assertEqual(safe_cell(moment), "2026-03-01")

    def test_the_pdf_stamp_is_indian_time_as_it_claims(self):
        moment = datetime(2026, 2, 28, 18, 45, tzinfo=utc.utc)

        with patch("apps.dashboard.exports.timezone.now", return_value=moment):
            self.assertEqual(generated_stamp(), "Generated 01 Mar 2026, 00:15 IST")

    def test_the_summary_is_a_real_pdf(self):
        response = self.get("dashboard-pdf")

        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))
        self.assertIn("attachment", response["Content-Disposition"])

    def test_indian_grouping(self):
        self.assertEqual(indian_number(Decimal("1234567.50")), "12,34,567.50")
        self.assertEqual(indian_number(Decimal("999.00")), "999.00")
        self.assertEqual(indian_number(Decimal("100000.00")), "1,00,000.00")
        self.assertEqual(indian_number(Decimal("-1500.00")), "-1,500.00")


# ============================================================
# Permissions and speed
# ============================================================

class DashboardPermissionTests(DashboardTestCase):
    def urls(self):
        return [reverse("dashboard"), reverse("dashboard-metric", args=["cash_paid"]),
                reverse("dashboard-csv", args=["cash_paid"]), reverse("dashboard-pdf")]

    def test_the_director_and_administrator_may_read(self):
        admin = User.objects.create_user("dash_admin", roles=[Role.ADMINISTRATOR])
        for user in (self.director, admin):
            self.client.force_login(user)
            for url in self.urls():
                self.assertEqual(self.client.get(url).status_code, 200, f"{user} {url}")

    def test_every_other_role_is_refused(self):
        for role in (Role.SALES, Role.OPERATIONS_MANAGER, Role.WAREHOUSE, Role.TECHNICIAN,
                     Role.SUPPORT, Role.FINANCE):
            self.client.force_login(User.objects.create_user(f"dash_{role}", roles=[role]))
            for url in self.urls():
                self.assertEqual(self.client.get(url).status_code, 403, f"{role} {url}")

    def test_there_is_no_anonymous_financial_view(self):
        self.client.logout()

        for url in self.urls():
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_nobody_writes_here(self):
        self.assertEqual(self.client.post(reverse("dashboard"), {}, content_type=JSON).status_code,
                         403)


class SpeedTests(DashboardTestCase):
    def test_more_records_do_not_mean_more_queries(self):
        """Drill rows may grow, but the query count must not grow with them."""
        self.complete_the_job()
        chosen = filters(start=date(2020, 1, 1))

        with CaptureQueriesContext(connection) as before:
            dashboard(chosen)
        for _ in range(3):
            self.raise_ticket()
        with CaptureQueriesContext(connection) as after:
            dashboard(chosen)

        self.assertLessEqual(len(after), len(before) + len(GROUPS))

    def test_operational_margin_is_read_from_the_costing_function(self):
        """One definition, so the order screen and the dashboard cannot differ."""
        self.complete_the_job()

        order = Order.objects.select_related("quotation").get(pk=self.order.pk)

        rows = operational_margin(filters())
        self.assertEqual(rows[0]["amount"], costs_for_orders([order])[order.pk]["operational_margin"])
