"""
F09 - what reservation, scanning and dispatch have to prove.

The expensive mistakes: two orders holding the same inverter, a box
sealed with something missing, goods going out before the money has
cleared, and a warranty clock that starts at the wrong moment.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.catalogue.models import Product, TrackingMethod
from apps.core.api import business_date
from apps.inventory.models import (BatchLot, PurchaseOrder, PurchaseStatus,
                                   PurchaseOrderLine, SerializedUnit, StockStatus,
                                   Supplier)
from apps.inventory.services import receive_goods
from apps.orders.models import Order, OrderStatus, PaymentStatus
from apps.quotations.test_acceptance import signature_file
from apps.quotations.tests import seed_quote_context

from .models import Fulfilment, FulfilmentStatus, PackingLine

User = get_user_model()
JSON = "application/json"

# Which fixture products become one-unit-at-a-time stock.
SERIALIZED_SKUS = ["PANEL", "INV"]


class FulfilmentFixture:
    """
    Builds a paid, confirmed order with stock on the shelf behind it.

    A mixin so the concurrency tests in F12 can run the same journey on
    a TransactionTestCase, where threads see each other's commits.
    """

    def setUp(self):
        (self.admin, self.sales, self.technician,
         self.enquiry, self.survey, self.package) = seed_quote_context()
        self.finance = User.objects.create_user("ful_finance", roles=[Role.FINANCE])
        self.warehouse = User.objects.create_user("ful_wh", roles=[Role.WAREHOUSE])
        self.manager = User.objects.create_user(
            "ful_mgr", roles=[Role.OPERATIONS_MANAGER]
        )

        # Panels and inverters carry serials; everything else is bulk.
        Product.objects.filter(sku__in=SERIALIZED_SKUS).update(
            tracking_method=TrackingMethod.SERIALIZED
        )

        self.order = self._accepted_order()
        self._clear_the_advance()
        self.supplier = Supplier.objects.create(name="Test Supplier")

    # --- setup helpers -------------------------------------------------

    def _accepted_order(self):
        self.client.force_login(self.sales)
        quote = self.client.post(
            reverse("quotation-generate"),
            {"enquiry": self.enquiry.pk, "idempotency_key": "gen"},
            content_type=JSON,
        ).json()
        issued = self.client.post(
            reverse("quotation-action", args=[quote["id"], "issue"]),
            {"revision": quote["revision"], "idempotency_key": "issue"},
            content_type=JSON,
        ).json()
        self.client.post(
            reverse("quotation-accept", args=[issued["id"]]),
            {"revision": issued["revision"], "idempotency_key": "accept",
             "customer_name": "Ramesh Gupta", "signature": signature_file()},
        )
        response = self.client.post(
            reverse("order-confirm"), {"quotation": issued["id"]}, content_type=JSON
        )
        return Order.objects.get(pk=response.json()["id"])

    def _clear_the_advance(self):
        self.client.force_login(self.finance)
        self.client.post(
            reverse("payment-create", args=[self.order.pk]),
            {"amount": str(self.order.advance_payable), "method": "upi",
             "external_reference": "UPI-ADV", "status": PaymentStatus.CLEARED,
             "paid_on": str(business_date())},
            content_type=JSON,
        )

    def stock_everything(self, *, shortfall_sku=None):
        """Receives enough of every packing line, optionally leaving one short."""
        fulfilment = self.opened()
        purchase = PurchaseOrder.objects.create(
            supplier=self.supplier, raised_by=self.warehouse,
            status=PurchaseStatus.PLACED,
        )
        rows = []
        for line in fulfilment.lines.select_related("product"):
            wanted = line.required_quantity
            if line.sku == shortfall_sku:
                wanted = wanted - 1
            if wanted <= 0:
                continue

            po_line = PurchaseOrderLine.objects.create(
                purchase_order=purchase, product=line.product,
                quantity=wanted, unit_cost="10.00",
            )
            if line.tracking_method == TrackingMethod.SERIALIZED:
                rows.append({"line": po_line.pk, "serial_numbers": [
                    f"{line.sku}-{index + 1}" for index in range(int(wanted))
                ]})
            else:
                rows.append({"line": po_line.pk, "batch_id": f"BATCH-{line.sku}",
                             "quantity": str(wanted)})

        receive_goods(purchase.pk, {
            "received_on": business_date(), "lines": rows,
        }, self.warehouse)
        return fulfilment

    # --- action helpers ------------------------------------------------

    def opened(self):
        self.client.force_login(self.warehouse)
        response = self.client.post(
            reverse("fulfilment-open"), {"order": self.order.pk}, content_type=JSON
        )
        return Fulfilment.objects.get(pk=response.json()["id"])

    def reserve(self, fulfilment):
        self.client.force_login(self.warehouse)
        return self.client.post(reverse("fulfilment-reserve", args=[fulfilment.pk]))

    def scan(self, fulfilment, code, quantity=None, **extra):
        self.client.force_login(extra.pop("actor", self.warehouse))
        payload = {"code": code, **extra}
        if quantity is not None:
            payload["quantity"] = str(quantity)
        return self.client.post(
            reverse("fulfilment-scan", args=[fulfilment.pk]), payload,
            content_type=JSON,
        )

    def scan_everything(self, fulfilment):
        for line in fulfilment.lines.all():
            if line.tracking_method == TrackingMethod.SERIALIZED:
                for unit in SerializedUnit.objects.filter(
                        product=line.product, order=self.order):
                    self.scan(fulfilment, unit.asset_id)
            else:
                lot = BatchLot.objects.filter(
                    product=line.product, order=self.order,
                    status=StockStatus.RESERVED).first()
                self.scan(fulfilment, lot.batch_id, quantity=line.required_quantity)


class FulfilmentTestCase(FulfilmentFixture, TestCase):
    pass


class ChecklistTests(FulfilmentTestCase):
    def test_the_checklist_comes_from_the_order(self):
        """Opening reserves in the same action, so it never rests at Pending."""
        fulfilment = self.opened()

        self.assertTrue(fulfilment.lines.exists())
        self.assertNotEqual(fulfilment.status, FulfilmentStatus.PENDING)

    def test_opening_with_nothing_on_the_shelf_blocks_immediately(self):
        fulfilment = self.opened()

        self.assertEqual(fulfilment.status, FulfilmentStatus.BLOCKED)
        self.assertIn("purchase order", fulfilment.blocked_reason)

    def test_labour_is_not_on_the_packing_list(self):
        """Nobody can scan a job of labour into a box."""
        fulfilment = self.opened()

        self.assertNotIn("LABOUR", [line.sku for line in fulfilment.lines.all()])

    def test_opening_twice_returns_the_same_checklist(self):
        first = self.opened()
        second = self.opened()

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Fulfilment.objects.count(), 1)


class ReservationTests(FulfilmentTestCase):
    def test_reserving_claims_the_stock(self):
        fulfilment = self.stock_everything()

        self.reserve(fulfilment)

        fulfilment.refresh_from_db()
        self.assertEqual(fulfilment.status, FulfilmentStatus.RESERVED)
        self.assertTrue(SerializedUnit.objects.filter(
            order=self.order, status=StockStatus.RESERVED).exists())

    def test_a_shortage_blocks_and_says_what_to_buy(self):
        """Half a system never goes to a roof: the whole order blocks."""
        fulfilment = self.stock_everything(shortfall_sku="PANEL")

        self.reserve(fulfilment)

        fulfilment.refresh_from_db()
        self.assertEqual(fulfilment.status, FulfilmentStatus.BLOCKED)
        self.assertIn("PANEL", fulfilment.blocked_reason)
        self.assertIn("purchase order", fulfilment.blocked_reason)
        # Nothing was left half-claimed.
        self.assertFalse(SerializedUnit.objects.filter(
            status=StockStatus.RESERVED).exists())

    def test_two_orders_never_hold_the_same_unit(self):
        fulfilment = self.stock_everything()
        self.reserve(fulfilment)

        held = SerializedUnit.objects.filter(order=self.order,
                                             status=StockStatus.RESERVED).count()
        free = SerializedUnit.objects.filter(status=StockStatus.AVAILABLE).count()

        self.assertGreater(held, 0)
        self.assertEqual(free, 0)


class ScanningTests(FulfilmentTestCase):
    def setUp(self):
        super().setUp()
        self.fulfilment = self.stock_everything()
        self.reserve(self.fulfilment)
        self.panel = SerializedUnit.objects.filter(
            product__sku="PANEL", order=self.order).first()

    def test_scanning_a_unit_packs_it(self):
        response = self.scan(self.fulfilment, self.panel.asset_id)

        self.assertEqual(response.status_code, 201, response.content)
        line = PackingLine.objects.get(fulfilment=self.fulfilment,
                                       product=self.panel.product)
        self.assertEqual(line.packed_quantity, Decimal("1.00"))

    def test_the_same_unit_cannot_be_scanned_twice(self):
        self.scan(self.fulfilment, self.panel.asset_id)

        again = self.scan(self.fulfilment, self.panel.asset_id)

        self.assertEqual(again.status_code, 400)
        self.assertIn("already in the box", str(again.content))

    def test_a_unit_not_held_for_this_order_is_refused(self):
        """Reserved against nothing is as wrong as reserved for someone else."""
        SerializedUnit.objects.filter(pk=self.panel.pk).update(order=None)

        response = self.scan(self.fulfilment, self.panel.asset_id)

        self.assertEqual(response.status_code, 400)
        self.assertIn("not reserved for this order", str(response.content))

    def test_an_already_dispatched_unit_is_refused(self):
        SerializedUnit.objects.filter(pk=self.panel.pk).update(
            status=StockStatus.DISPATCHED)

        response = self.scan(self.fulfilment, self.panel.asset_id)

        self.assertEqual(response.status_code, 400)
        self.assertIn("already left the warehouse", str(response.content))

    def test_an_unknown_code_is_refused(self):
        response = self.scan(self.fulfilment, "NOT-A-REAL-CODE", quantity="1")

        self.assertEqual(response.status_code, 400)

    def test_a_batch_needs_a_counted_quantity(self):
        lot = BatchLot.objects.filter(order=self.order).first()

        response = self.scan(self.fulfilment, lot.batch_id)

        self.assertEqual(response.status_code, 400)
        self.assertIn("counted quantity", str(response.content))

    def test_manual_entry_needs_a_manager_and_a_reason(self):
        refused = self.scan(self.fulfilment, self.panel.asset_id,
                            entered_manually=True, manual_reason="Label torn")
        self.assertEqual(refused.status_code, 400)

        allowed = self.scan(self.fulfilment, self.panel.asset_id, actor=self.manager,
                            entered_manually=True, manual_reason="Label torn")
        self.assertEqual(allowed.status_code, 201, allowed.content)

    def test_manual_entry_without_a_reason_is_refused(self):
        response = self.scan(self.fulfilment, self.panel.asset_id, actor=self.manager,
                             entered_manually=True)

        self.assertEqual(response.status_code, 400)


class DispatchTests(FulfilmentTestCase):
    def setUp(self):
        super().setUp()
        self.fulfilment = self.stock_everything()
        self.reserve(self.fulfilment)

    def close(self):
        self.fulfilment.refresh_from_db()
        return self.client.post(
            reverse("fulfilment-close", args=[self.fulfilment.pk]),
            {"revision": self.fulfilment.revision}, content_type=JSON,
        )

    def test_the_box_cannot_be_sealed_while_something_is_missing(self):
        response = self.close()

        self.assertEqual(response.status_code, 400)
        self.assertIn("Not everything is packed", str(response.content))

    def test_a_fully_packed_order_seals(self):
        self.scan_everything(self.fulfilment)

        response = self.close()

        self.assertEqual(response.status_code, 200, response.content)
        self.fulfilment.refresh_from_db()
        self.assertEqual(self.fulfilment.status, FulfilmentStatus.PACKED)

    def test_dispatch_waits_for_cleared_money(self):
        self.scan_everything(self.fulfilment)
        self.close()
        # Reverse the advance, so nothing has cleared any more.
        from apps.orders.models import Payment
        payment = Payment.objects.get()
        self.client.force_login(self.finance)
        self.client.post(reverse("payment-reverse", args=[payment.pk]),
                         {"revision": payment.revision, "reason": "Bounced"},
                         content_type=JSON)

        self.fulfilment.refresh_from_db()
        self.client.force_login(self.warehouse)
        response = self.client.post(
            reverse("fulfilment-dispatch", args=[self.fulfilment.pk]),
            {"revision": self.fulfilment.revision}, content_type=JSON,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("held until", str(response.content))

    def test_delivery_is_what_makes_the_balance_due(self):
        self.scan_everything(self.fulfilment)
        self.close()
        self.fulfilment.refresh_from_db()

        self.client.force_login(self.warehouse)
        self.client.post(reverse("fulfilment-dispatch", args=[self.fulfilment.pk]),
                         {"revision": self.fulfilment.revision}, content_type=JSON)
        self.fulfilment.refresh_from_db()
        response = self.client.post(
            reverse("fulfilment-deliver", args=[self.fulfilment.pk]),
            {"revision": self.fulfilment.revision,
             "delivered_at": timezone.now().isoformat(),
             "received_by_name": "Ramesh Gupta"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.DELIVERED)
        self.assertEqual(self.order.balance_due_on, business_date())
        # The equipment is now the customer's, and traceable to the roof.
        unit = SerializedUnit.objects.filter(order=self.order).first()
        self.assertEqual(unit.status, StockStatus.DELIVERED)
        self.assertEqual(unit.customer_id, self.order.customer_id)

    def test_delivery_cannot_be_recorded_in_the_future(self):
        self.scan_everything(self.fulfilment)
        self.close()
        self.fulfilment.refresh_from_db()
        self.client.post(reverse("fulfilment-dispatch", args=[self.fulfilment.pk]),
                         {"revision": self.fulfilment.revision}, content_type=JSON)
        self.fulfilment.refresh_from_db()

        response = self.client.post(
            reverse("fulfilment-deliver", args=[self.fulfilment.pk]),
            {"revision": self.fulfilment.revision,
             "delivered_at": (timezone.now() + timedelta(days=1)).isoformat(),
             "received_by_name": "Ramesh Gupta"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 400)
