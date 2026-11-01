"""
The demo seed: six months of history plus a customer at every stage.

It must build every stage it promises, replay the past on the days it
happened rather than all today, and never touch a database that already
has real enquiries in it.
"""

import io
import shutil
import tempfile
from datetime import timedelta

from django.core.cache import cache
from django.core.management import CommandError, call_command
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings

from apps.catalogue.models import PackageTemplate, PackageVersion, Product
from apps.core.api import business_date
from apps.customers.models import Enquiry, EnquiryStatus
from apps.fulfilment.models import Fulfilment, FulfilmentStatus
from apps.inventory.models import SerializedUnit, StockStatus
from apps.orders.models import Order, OrderStatus
from apps.quotations.models import QuoteRevision
from apps.scheduling.models import Job, JobKind, JobStatus
from apps.support.models import ServiceTicket
from apps.surveys.models import SurveyRevision
from apps.warranties.models import AssetWarranty


class SeedDemoTests(TestCase):
    @classmethod
    def setUpClass(cls):
        # Uploads and the label sheet go to a folder removed afterwards.
        # Before super(): that is where setUpTestData runs the seed.
        cls.media_root = tempfile.mkdtemp()
        cls.media = override_settings(MEDIA_ROOT=cls.media_root)
        cls.media.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        cls.media.disable()
        shutil.rmtree(cls.media_root, ignore_errors=True)
        super().tearDownClass()

    @classmethod
    def setUpTestData(cls):
        cache.clear()
        cls.output = io.StringIO()
        cls.labels = f"{cls.media_root}/labels.pdf"
        call_command("seed_demo", labels=cls.labels, stdout=cls.output)

    def test_every_sales_stage_has_a_customer_waiting(self):
        statuses = set(Enquiry.objects.values_list("status", flat=True))
        self.assertTrue({EnquiryStatus.NEW, EnquiryStatus.SURVEY_SCHEDULED,
                         EnquiryStatus.LOST} <= statuses)
        self.assertTrue(Enquiry.objects.filter(owner__isnull=True).exists())
        self.assertTrue(any(enquiry.is_overdue for enquiry in Enquiry.objects.all()))
        revisions = set(SurveyRevision.objects.values_list("status", flat=True))
        self.assertTrue({"submitted", "approved"} <= revisions)
        quotes = set(QuoteRevision.objects.values_list("status", flat=True))
        self.assertTrue({"draft", "issued", "accepted"} <= quotes)
        self.assertTrue(QuoteRevision.objects.filter(status="accepted", order__isnull=True).exists())

    def test_every_order_stage_is_there(self):
        unpaid = [order for order in Order.objects.filter(status=OrderStatus.CONFIRMED)
                  if not order.dispatch_allowed]
        self.assertTrue(unpaid)
        self.assertTrue(Fulfilment.objects.filter(status=FulfilmentStatus.RESERVED,
                                                  order__status=OrderStatus.CONFIRMED).exists())
        self.assertTrue(Job.objects.filter(kind=JobKind.INSTALLATION,
                                           status=JobStatus.AWAITING_SCHEDULING).exists())
        self.assertTrue(Job.objects.filter(kind=JobKind.INSTALLATION, status=JobStatus.SCHEDULED,
                                           order__fulfilment__status=FulfilmentStatus.DELIVERED)
                        .exists())

    def test_the_history_is_spread_over_six_months_not_all_today(self):
        completed = Order.objects.filter(status=OrderStatus.COMPLETED)
        self.assertGreaterEqual(completed.count(), 12)
        dates = sorted(order.confirmed_at.date() for order in completed)
        self.assertGreater((dates[-1] - dates[0]).days, 120)
        self.assertLess(dates[0], business_date() - timedelta(days=120))
        # Derived dates follow the day it happened: a warranty starts at its delivery.
        oldest = AssetWarranty.objects.order_by("coverage_start").first()
        self.assertLess(oldest.coverage_start, business_date() - timedelta(days=120))

    def test_a_cancelled_order_gave_its_stock_back_and_its_money(self):
        cancelled = Order.objects.get(status=OrderStatus.CANCELLED)
        self.assertEqual(cancelled.fulfilment.status, FulfilmentStatus.CANCELLED)
        self.assertFalse(SerializedUnit.objects.filter(order=cancelled).exists())
        self.assertTrue(cancelled.payments.filter(kind="refund").exists())

    def test_delivery_issued_warranties_and_stock_is_left_to_sell(self):
        """Every delivered unit whose product has a policy is covered, inverters included."""
        delivered = SerializedUnit.objects.filter(
            status__in=[StockStatus.DELIVERED, StockStatus.INSTALLED])
        self.assertTrue(delivered.filter(product__category="inverter").exists())
        self.assertFalse(delivered.filter(product__warranty_policy__isnull=True).exists())
        self.assertEqual(AssetWarranty.objects.count(), delivered.count())
        self.assertTrue(SerializedUnit.objects.filter(status=StockStatus.AVAILABLE).exists())

    def test_the_catalogue_reads_as_real_parts_and_systems(self):
        self.assertFalse(Product.objects.filter(name__icontains="dummy").exists())
        self.assertFalse(PackageTemplate.objects.filter(name__icontains="dummy").exists())
        self.assertFalse(PackageVersion.objects.filter(notes__icontains="dummy").exists())
        self.assertFalse(PackageVersion.objects.filter(status="draft").exists())

    def test_support_has_new_closed_and_uncovered_tickets(self):
        statuses = list(ServiceTicket.objects.values_list("status", flat=True))
        self.assertIn("new", statuses)
        self.assertGreaterEqual(statuses.count("closed"), 2)
        self.assertTrue(ServiceTicket.objects.filter(assets__assessment="not_covered").exists())
        new = ServiceTicket.objects.get(status="new")
        self.assertTrue(all(asset.assessment == "covered" for asset in new.assets.all()))

    def test_it_saves_the_labels_and_says_how_to_sign_in(self):
        with open(self.labels, "rb") as sheet:
            self.assertTrue(sheet.read().startswith(b"%PDF-"))
        self.assertIn("demo-pass-123", self.output.getvalue())

    def test_it_refuses_a_database_with_enquiries_in_it(self):
        count = Enquiry.objects.count()
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=io.StringIO())
        self.assertEqual(Enquiry.objects.count(), count)

    def test_customer_history_includes_order_amounts(self):
        order = Order.objects.filter(status=OrderStatus.COMPLETED).first()
        self.client.force_login(get_user_model().objects.get(username="sales_anita"))

        response = self.client.get(f"/api/v1/customers/{order.customer_id}/")

        self.assertEqual(response.status_code, 200)
        recorded = next(row for row in response.json()["orders"] if row["id"] == order.pk)
        self.assertEqual(recorded["gross"], str(order.gross_payable))
        self.assertEqual(recorded["outstanding"], str(order.outstanding()))
