"""
F08 - what the stock rules have to prove.

The claim this feature makes is "every item is accounted for and
scanned, at the identity its physical form actually supports". So: a
panel arrives with a serial and gets its own row, cable arrives as a
batch with a quantity and nobody invents a serial for it, and no stock
anywhere changes state without a movement explaining it.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from rest_framework.exceptions import ValidationError as ApiValidationError

from apps.accounts.models import Role
from apps.catalogue.models import Category, Product, TrackingMethod
from apps.core.api import business_date

from .models import (BatchLot, MovementReason, PurchaseOrder, PurchaseOrderLine,
                     PurchaseStatus, SerializedUnit, StockMovement, StockStatus, Supplier)
from .services import move_stock

User = get_user_model()
JSON = "application/json"


def make_product(sku, tracking, unit="piece", **extra):
    return Product.objects.create(
        sku=sku, name=f"Test {sku}", category=extra.pop("category", Category.PANEL),
        tracking_method=tracking, unit=unit, gst_rate_percent="12.00", **extra
    )


class InventoryTestCase(TestCase):
    def setUp(self):
        self.warehouse = User.objects.create_user("wh", roles=[Role.WAREHOUSE])
        self.sales = User.objects.create_user("stock_sales", roles=[Role.SALES])
        self.supplier = Supplier.objects.create(name="Sunrise Distributors")

        self.panel = make_product("PNL-TEST", TrackingMethod.SERIALIZED)
        self.cable = make_product("CBL-TEST", TrackingMethod.BULK, unit="m",
                                  category=Category.CABLE)

        self.client.force_login(self.warehouse)

    def placed_purchase(self, product, quantity, unit_cost="100.00"):
        purchase = PurchaseOrder.objects.create(
            supplier=self.supplier, raised_by=self.warehouse, status=PurchaseStatus.PLACED
        )
        line = PurchaseOrderLine.objects.create(
            purchase_order=purchase, product=product,
            quantity=Decimal(quantity), unit_cost=Decimal(unit_cost),
        )
        return purchase, line

    def receive(self, purchase, rows, received_on=None):
        return self.client.post(
            reverse("purchase-receive", args=[purchase.pk]),
            {"received_on": str(received_on or business_date()), "lines": rows},
            content_type=JSON,
        )


class ReceivingTests(InventoryTestCase):
    def test_a_serialized_product_becomes_one_row_per_unit(self):
        purchase, line = self.placed_purchase(self.panel, "3")

        response = self.receive(purchase, [
            {"line": line.pk, "serial_numbers": ["SN-001", "SN-002", "SN-003"]}
        ])

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(SerializedUnit.objects.count(), 3)
        unit = SerializedUnit.objects.get(serial_number="SN-001")
        self.assertTrue(unit.asset_id.startswith("AST-"))
        self.assertEqual(unit.status, StockStatus.AVAILABLE)
        self.assertEqual(unit.acquisition_cost, Decimal("100.00"))

    def test_a_bulk_product_becomes_one_lot_with_a_quantity(self):
        purchase, line = self.placed_purchase(self.cable, "500", unit_cost="48.00")

        response = self.receive(purchase, [
            {"line": line.pk, "batch_id": "DRUM-77", "quantity": "500.00"}
        ])

        self.assertEqual(response.status_code, 201, response.content)
        lot = BatchLot.objects.get()
        self.assertEqual(lot.batch_id, "DRUM-77")
        self.assertEqual(lot.quantity, Decimal("500.00"))
        self.assertEqual(lot.unit, "m")
        self.assertFalse(SerializedUnit.objects.exists())

    def test_cable_is_not_given_a_made_up_serial(self):
        purchase, line = self.placed_purchase(self.cable, "100")

        response = self.receive(purchase, [
            {"line": line.pk, "serial_numbers": ["CABLE-001"]}
        ])

        self.assertEqual(response.status_code, 400)
        self.assertFalse(BatchLot.objects.exists())

    def test_a_panel_cannot_be_booked_in_as_a_batch(self):
        purchase, line = self.placed_purchase(self.panel, "2")

        response = self.receive(purchase, [
            {"line": line.pk, "batch_id": "BOX-1", "quantity": "2"}
        ])

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SerializedUnit.objects.exists())

    def test_receiving_more_than_was_ordered_is_refused(self):
        purchase, line = self.placed_purchase(self.panel, "2")

        response = self.receive(purchase, [
            {"line": line.pk, "serial_numbers": ["SN-1", "SN-2", "SN-3"]}
        ])

        self.assertEqual(response.status_code, 400)
        self.assertFalse(SerializedUnit.objects.exists())

    def test_the_same_serial_cannot_arrive_twice(self):
        purchase, line = self.placed_purchase(self.panel, "2")
        self.receive(purchase, [{"line": line.pk, "serial_numbers": ["SN-DUP"]}])

        again = self.receive(purchase, [{"line": line.pk, "serial_numbers": ["SN-DUP"]}])

        self.assertEqual(again.status_code, 400)
        self.assertEqual(SerializedUnit.objects.count(), 1)

    def test_goods_cannot_arrive_in_the_future(self):
        purchase, line = self.placed_purchase(self.panel, "1")

        response = self.receive(purchase, [{"line": line.pk, "serial_numbers": ["SN-X"]}],
                                received_on=business_date() + timedelta(days=1))

        self.assertEqual(response.status_code, 400)

    def test_a_part_delivery_leaves_the_order_open(self):
        purchase, line = self.placed_purchase(self.panel, "3")

        self.receive(purchase, [{"line": line.pk, "serial_numbers": ["SN-A"]}])

        purchase.refresh_from_db()
        line.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.PART_RECEIVED)
        self.assertEqual(line.outstanding_quantity, Decimal("2.00"))

    def test_the_last_delivery_closes_the_order(self):
        purchase, line = self.placed_purchase(self.panel, "2")

        self.receive(purchase, [{"line": line.pk, "serial_numbers": ["SN-A", "SN-B"]}])

        purchase.refresh_from_db()
        self.assertEqual(purchase.status, PurchaseStatus.RECEIVED)


class MovementTests(InventoryTestCase):
    def setUp(self):
        super().setUp()
        purchase, line = self.placed_purchase(self.panel, "1")
        self.receive(purchase, [{"line": line.pk, "serial_numbers": ["SN-MOVE"]}])
        self.unit = SerializedUnit.objects.get()

    def test_arriving_is_itself_a_movement(self):
        movement = StockMovement.objects.get(unit=self.unit)

        self.assertEqual(movement.reason, MovementReason.RECEIPT)
        self.assertEqual(movement.from_status, "")
        self.assertEqual(movement.to_status, StockStatus.AVAILABLE)

    def test_every_change_of_state_writes_a_movement(self):
        move_stock(self.warehouse, unit=self.unit, to_status=StockStatus.RESERVED,
                   reason=MovementReason.RESERVATION)

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, StockStatus.RESERVED)
        self.assertEqual(StockMovement.objects.filter(unit=self.unit).count(), 2)

    def test_an_impossible_move_is_refused(self):
        """Stock cannot be installed straight off the shelf."""
        with self.assertRaises(ApiValidationError):
            move_stock(self.warehouse, unit=self.unit, to_status=StockStatus.INSTALLED,
                       reason=MovementReason.INSTALLATION)

        self.unit.refresh_from_db()
        self.assertEqual(self.unit.status, StockStatus.AVAILABLE)

    def test_stock_history_is_append_only(self):
        movement = StockMovement.objects.get(unit=self.unit)

        movement.to_status = StockStatus.INSTALLED
        with self.assertRaises(ValidationError):
            movement.save()
        with self.assertRaises(ValidationError):
            movement.delete()

    def test_a_unit_is_never_deleted(self):
        with self.assertRaises(ValidationError):
            self.unit.delete()


class PartialLotTests(InventoryTestCase):
    def test_taking_part_of_a_lot_leaves_the_rest_on_the_shelf(self):
        purchase, line = self.placed_purchase(self.cable, "500", unit_cost="48.00")
        self.receive(purchase, [
            {"line": line.pk, "batch_id": "DRUM-9", "quantity": "500.00"}
        ])
        lot = BatchLot.objects.get()

        taken = move_stock(self.warehouse, lot=lot, to_status=StockStatus.RESERVED,
                           reason=MovementReason.RESERVATION, quantity=Decimal("120.00"))

        lot.refresh_from_db()
        self.assertEqual(lot.quantity, Decimal("380.00"))
        self.assertEqual(lot.status, StockStatus.AVAILABLE)
        self.assertEqual(taken.quantity, Decimal("120.00"))
        self.assertEqual(taken.status, StockStatus.RESERVED)
        self.assertEqual(taken.batch_id, "DRUM-9")

    def test_more_cannot_be_taken_than_the_lot_holds(self):
        purchase, line = self.placed_purchase(self.cable, "50")
        self.receive(purchase, [{"line": line.pk, "batch_id": "DRUM-2", "quantity": "50"}])
        lot = BatchLot.objects.get()

        with self.assertRaises(ApiValidationError):
            move_stock(self.warehouse, lot=lot, to_status=StockStatus.RESERVED,
                       reason=MovementReason.RESERVATION, quantity=Decimal("80.00"))


class PermissionTests(InventoryTestCase):
    def test_sales_cannot_see_stock_because_it_carries_cost(self):
        self.client.force_login(self.sales)

        response = self.client.get(reverse("stock-units"))

        self.assertEqual(response.status_code, 403)
