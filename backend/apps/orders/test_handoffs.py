"""
F07 hand-offs: what confirming and cancelling an order must do downstream.

Confirming creates the warehouse requirement and the installation
awaiting scheduling, exactly once, and nothing that goes wrong with the
stock may undo a valid order. Cancelling gives the stock back. The
waiting installation has no invented date, and only booking gives it one.
"""

import threading
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Role
from apps.catalogue.models import Category, Product, TrackingMethod
from apps.core.api import business_date
from apps.core.models import AuditEvent
from apps.fulfilment.models import Fulfilment, FulfilmentStatus
from apps.fulfilment.tests import FulfilmentFixture
from apps.inventory.models import (BatchLot, MovementReason, PurchaseOrder, PurchaseOrderLine,
                                   PurchaseStatus, SerializedUnit, StockMovement, StockStatus)
from apps.inventory.services import receive_goods
from apps.quotations.models import QuoteRevision
from apps.quotations.test_acceptance import signature_file
from apps.scheduling.models import Job, JobKind, JobStatus

from .models import Order, OrderStatus

User = get_user_model()
JSON = "application/json"


# ============================================================
# Fixture
# ============================================================

class HandoffFixture(FulfilmentFixture):
    """An accepted quotation that each test confirms when it is ready."""

    def _accepted_order(self):
        self.client.force_login(self.sales)
        quote = self.client.post(reverse("quotation-generate"),
                                 {"enquiry": self.enquiry.pk, "idempotency_key": "gen"},
                                 content_type=JSON).json()
        issued = self.client.post(reverse("quotation-action", args=[quote["id"], "issue"]),
                                  {"revision": quote["revision"], "idempotency_key": "issue"},
                                  content_type=JSON).json()
        self.client.post(reverse("quotation-accept", args=[issued["id"]]),
                         {"revision": issued["revision"], "idempotency_key": "accept",
                          "customer_name": "Ramesh Gupta", "signature": signature_file()})
        self.quotation = QuoteRevision.objects.get(pk=issued["id"])
        return None

    def _clear_the_advance(self):
        """Money is not the point here; dispatch gating is tested in F09."""

    def confirm(self, client=None):
        client = client or self.client
        client.force_login(self.sales)
        return client.post(reverse("order-confirm"), {"quotation": self.quotation.pk},
                           content_type=JSON)

    def confirmed(self):
        response = self.confirm()
        self.assertEqual(response.status_code, 201, response.content)
        return Order.objects.get(pk=response.json()["id"])

    def physical_lines(self):
        return self.quotation.lines.select_related("product").exclude(
            product__tracking_method=TrackingMethod.SERVICE).exclude(
            product__category=Category.SERVICE)

    def put_stock_on_the_shelf(self):
        """Receives exactly what the quotation needs, before it is confirmed."""
        purchase = PurchaseOrder.objects.create(supplier=self.supplier, raised_by=self.warehouse,
                                                status=PurchaseStatus.PLACED)
        rows = []
        for line in self.physical_lines():
            po_line = PurchaseOrderLine.objects.create(purchase_order=purchase, product=line.product,
                                                       quantity=line.quantity, unit_cost="10.00")
            if line.product.tracking_method == TrackingMethod.SERIALIZED:
                rows.append({"line": po_line.pk, "serial_numbers": [
                    f"{line.sku}-{index + 1}" for index in range(int(line.quantity))]})
            else:
                rows.append({"line": po_line.pk, "batch_id": f"BATCH-{line.sku}",
                             "quantity": str(line.quantity)})
        receive_goods(purchase.pk, {"received_on": business_date(), "lines": rows}, self.warehouse)

    def book(self, job, technicians=None, actor=None, hours=(10, 14)):
        self.client.force_login(actor or self.manager)
        day = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=3)
        return self.client.post(reverse("job-action", args=[job.pk, "schedule"]), {
            "revision": job.revision,
            "starts_at": day.replace(hour=hours[0]).isoformat(),
            "ends_at": day.replace(hour=hours[1]).isoformat(),
            "technicians": technicians or [self.technician.pk],
        }, content_type=JSON)


class HandoffTestCase(HandoffFixture, TestCase):
    pass


# ============================================================
# Confirmation
# ============================================================

class ConfirmationHandoffTests(HandoffTestCase):
    def test_confirming_reserves_the_stock_and_opens_a_waiting_installation(self):
        self.put_stock_on_the_shelf()
        order = self.confirmed()

        fulfilment = Fulfilment.objects.get(order=order)
        self.assertEqual(fulfilment.status, FulfilmentStatus.RESERVED)
        job = Job.objects.get(order=order)
        self.assertEqual((job.kind, job.status), (JobKind.INSTALLATION, JobStatus.AWAITING_SCHEDULING))
        self.assertEqual(job.site_id, order.site_id)
        self.assertIsNone(job.starts_at)
        self.assertFalse(job.assignments.exists())

    def test_a_shortage_blocks_the_packing_list_but_keeps_the_order(self):
        order = self.confirmed()

        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        fulfilment = Fulfilment.objects.get(order=order)
        self.assertEqual(fulfilment.status, FulfilmentStatus.BLOCKED)
        self.assertIn("Raise a purchase order", fulfilment.blocked_reason)

    def test_stock_that_arrives_later_is_claimed_by_opening_the_list_again(self):
        order = self.confirmed()
        self.put_stock_on_the_shelf()

        self.client.force_login(self.warehouse)
        response = self.client.post(reverse("fulfilment-open"), {"order": order.pk}, content_type=JSON)

        self.assertEqual(response.json()["status"], FulfilmentStatus.RESERVED)
        self.assertEqual(Fulfilment.objects.filter(order=order).count(), 1)

    def test_a_reservation_that_fails_leaves_the_list_pending_not_the_order_undone(self):
        """Stock taken mid-claim by another order must not cancel this one."""
        self.put_stock_on_the_shelf()
        with patch("apps.fulfilment.services.reserve_stock",
                   side_effect=ValidationError({"stock": ["Taken while reserving."]})):
            order = self.confirmed()

        fulfilment = Fulfilment.objects.get(order=order)
        self.assertEqual(fulfilment.status, FulfilmentStatus.PENDING)
        self.assertFalse(SerializedUnit.objects.filter(status=StockStatus.RESERVED).exists())
        self.assertTrue(AuditEvent.objects.filter(action="reservation_deferred",
                                                  record_id=fulfilment.pk).exists())

    def test_confirming_twice_hands_off_once(self):
        first = self.confirmed()
        second = self.confirmed()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Fulfilment.objects.count(), 1)
        self.assertEqual(Job.objects.filter(kind=JobKind.INSTALLATION).count(), 1)

    def test_an_order_with_nothing_to_pack_gets_no_packing_list(self):
        Product.objects.update(tracking_method=TrackingMethod.SERVICE)
        order = self.confirmed()

        self.assertFalse(Fulfilment.objects.filter(order=order).exists())
        self.assertTrue(Job.objects.filter(order=order).exists())

    def test_the_order_shows_where_it_went(self):
        order = self.confirmed()
        self.client.force_login(self.finance)
        body = self.client.get(reverse("order-detail", args=[order.pk])).json()

        self.assertEqual(body["fulfilment"]["status"], FulfilmentStatus.BLOCKED)
        self.assertEqual(body["installation"]["status"], JobStatus.AWAITING_SCHEDULING)
        self.assertIsNone(body["installation"]["starts_at"])


# ============================================================
# The waiting installation
# ============================================================

class WaitingInstallationTests(HandoffTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.confirmed()
        self.job = Job.objects.get(order=self.order)

    def test_the_database_refuses_an_invented_date_or_a_missing_one(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Job.objects.filter(pk=self.job.pk).update(starts_at=timezone.now(),
                                                      ends_at=timezone.now() + timedelta(hours=1))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Job.objects.filter(pk=self.job.pk).update(status=JobStatus.SCHEDULED)

    def test_the_database_refuses_a_second_open_installation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Job.objects.create(kind=JobKind.INSTALLATION, status=JobStatus.AWAITING_SCHEDULING,
                               site=self.order.site, order=self.order, created_by=self.manager)

    def test_booking_gives_the_job_its_slot_and_crew(self):
        response = self.book(self.job)

        self.assertEqual(response.status_code, 200, response.content)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.SCHEDULED)
        self.assertIsNotNone(self.job.starts_at)
        lead = self.job.assignments.get(is_lead=True)
        self.assertEqual(lead.technician, self.technician)

    def test_a_busy_technician_leaves_the_job_waiting(self):
        """Refused bookings are all or nothing: no slot, no half a crew."""
        self.client.force_login(self.manager)
        day = timezone.now().replace(minute=0, second=0, microsecond=0) + timedelta(days=3)
        visit = self.client.post(reverse("job-create"), {
            "kind": JobKind.SERVICE, "site": self.order.site_id,
            "starts_at": day.replace(hour=9).isoformat(), "ends_at": day.replace(hour=17).isoformat(),
            "technicians": [self.technician.pk],
        }, content_type=JSON)
        self.assertEqual(visit.status_code, 201, visit.content)

        response = self.book(self.job, hours=(10, 12))

        self.assertEqual(response.status_code, 400)
        self.assertIn("technicians", response.json())
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, JobStatus.AWAITING_SCHEDULING)
        self.assertIsNone(self.job.starts_at)
        self.assertFalse(self.job.assignments.exists())

    def test_a_waiting_job_cannot_start_or_be_rescheduled(self):
        self.client.force_login(self.manager)
        start = self.client.post(reverse("job-action", args=[self.job.pk, "start"]),
                                 {"revision": self.job.revision}, content_type=JSON)
        move = self.client.post(reverse("job-action", args=[self.job.pk, "reschedule"]), {
            "revision": self.job.revision, "reason": "Customer asked",
            "starts_at": timezone.now().isoformat(),
            "ends_at": (timezone.now() + timedelta(hours=2)).isoformat(),
        }, content_type=JSON)

        self.assertEqual((start.status_code, move.status_code), (400, 400))

    def test_booking_the_order_installation_books_the_waiting_job(self):
        """'Book a visit' for the order must not create a second installation."""
        self.client.force_login(self.manager)
        start = timezone.now() + timedelta(days=2)
        response = self.client.post(reverse("job-create"), {
            "kind": JobKind.INSTALLATION, "site": self.order.site_id, "order": self.order.pk,
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=4)).isoformat(),
            "technicians": [self.technician.pk],
        }, content_type=JSON)

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["id"], self.job.pk)
        self.assertEqual(Job.objects.filter(order=self.order).count(), 1)

    def test_only_operations_may_book(self):
        for user in (self.sales, self.technician, self.warehouse):
            with self.subTest(user=user.username):
                self.assertEqual(self.book(self.job, actor=user).status_code, 403)

    def test_a_technician_is_not_shown_unassigned_work(self):
        self.client.force_login(self.technician)
        self.assertEqual(self.client.get(reverse("job-list")).json()["count"], 0)

    def test_an_order_confirmed_earlier_can_be_given_its_installation(self):
        """Orders confirmed before confirmation did this get it on request."""
        Job.objects.filter(pk=self.job.pk).update(status=JobStatus.CANCELLED)
        self.client.force_login(self.manager)
        url = reverse("job-open-installation")

        first = self.client.post(url, {"order": self.order.pk}, content_type=JSON)
        second = self.client.post(url, {"order": self.order.pk}, content_type=JSON)

        self.assertEqual(first.status_code, 201, first.content)
        self.assertEqual(first.json()["id"], second.json()["id"])
        self.assertEqual(first.json()["status"], JobStatus.AWAITING_SCHEDULING)


# ============================================================
# Cancellation
# ============================================================

class CancellationTests(HandoffTestCase):
    def cancel(self, order):
        order.refresh_from_db()
        self.client.force_login(self.sales)
        return self.client.post(reverse("order-cancel", args=[order.pk]),
                                {"revision": order.revision, "reason": "Customer withdrew"},
                                content_type=JSON)

    def test_cancelling_puts_the_reserved_stock_back_on_the_shelf(self):
        self.put_stock_on_the_shelf()
        order = self.confirmed()
        reserved_units = list(SerializedUnit.objects.filter(order=order).values_list("pk", flat=True))
        self.assertTrue(reserved_units)

        response = self.cancel(order)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(SerializedUnit.objects.filter(status=StockStatus.RESERVED).exists())
        self.assertFalse(BatchLot.objects.filter(status=StockStatus.RESERVED).exists())
        self.assertFalse(SerializedUnit.objects.filter(order=order).exists())
        released = StockMovement.objects.filter(reason=MovementReason.RELEASE)
        self.assertEqual(released.filter(unit_id__in=reserved_units).count(), len(reserved_units))
        self.assertEqual(Fulfilment.objects.get(order=order).status, FulfilmentStatus.CANCELLED)
        self.assertEqual(Job.objects.get(order=order).status, JobStatus.CANCELLED)
        self.assertEqual(response.json()["fulfilment"]["status"], FulfilmentStatus.CANCELLED)

    def test_cancelling_after_dispatch_is_refused_and_changes_nothing(self):
        self.put_stock_on_the_shelf()
        order = self.confirmed()
        Fulfilment.objects.filter(order=order).update(status=FulfilmentStatus.DISPATCHED)

        response = self.cancel(order)

        self.assertEqual(response.status_code, 400)
        order.refresh_from_db()
        self.assertEqual(order.status, OrderStatus.CONFIRMED)
        self.assertTrue(SerializedUnit.objects.filter(order=order).exists())
        self.assertEqual(Job.objects.get(order=order).status, JobStatus.AWAITING_SCHEDULING)


# ============================================================
# Concurrency, with real threads
# ============================================================

class SimultaneousConfirmationTests(HandoffFixture, TransactionTestCase):
    def test_two_people_confirming_at_once_hand_off_once(self):
        barrier = threading.Barrier(2)
        codes = []

        def confirm():
            try:
                client = Client(raise_request_exception=False)
                barrier.wait()
                codes.append(self.confirm(client).status_code)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=confirm) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(codes), [201, 201])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Fulfilment.objects.count(), 1)
        self.assertEqual(Job.objects.filter(kind=JobKind.INSTALLATION).count(), 1)
