"""
F08/F09 stock labels: the barcode must carry exactly what the packing scan
accepts, a split batch must still be labelled as it arrived, and only the
roles that see stock may print them.
"""

import math
import re
from decimal import Decimal

from django.urls import reverse

from apps.fulfilment.tests import FulfilmentTestCase
from apps.inventory.labels import LABELS_PER_PAGE, labels_for_order, labels_for_purchase
from apps.inventory.models import (BatchLot, MovementReason, PurchaseOrder, SerializedUnit,
                                   StockStatus)
from apps.inventory.services import move_stock

PAGE_OBJECT = re.compile(rb"/Type\s*/Page(?![a-z])")


class LabelTests(FulfilmentTestCase):
    def setUp(self):
        super().setUp()
        self.fulfilment = self.stock_everything()
        self.purchase = PurchaseOrder.objects.get()

    def fetch(self, user=None, **params):
        self.client.force_login(user or self.warehouse)
        return self.client.get(reverse("stock-labels"), params)

    def test_every_unit_and_batch_is_labelled_with_its_scan_code(self):
        codes = [label["code"] for label in labels_for_purchase(self.purchase)]

        units = SerializedUnit.objects.filter(goods_receipt__purchase_order=self.purchase)
        lots = BatchLot.objects.filter(goods_receipt__purchase_order=self.purchase)
        self.assertEqual(sorted(codes), sorted([unit.asset_id for unit in units]
                                               + [lot.batch_id for lot in lots]))

    def test_a_split_batch_is_still_labelled_as_received(self):
        """Reserving part of a batch must not shrink its receiving label."""
        lot = BatchLot.objects.filter(goods_receipt__purchase_order=self.purchase).first()
        received = lot.quantity
        move_stock(self.warehouse, lot=lot, to_status=StockStatus.RESERVED,
                   reason=MovementReason.RESERVATION, quantity=Decimal("1"), order=self.order)

        label = next(item for item in labels_for_purchase(self.purchase)
                     if item["code"] == lot.batch_id)
        self.assertIn(f"Batch of {received.normalize():f} ", label["lines"][0])
        self.assertEqual(sum(1 for item in labels_for_purchase(self.purchase)
                             if item["code"] == lot.batch_id), 1)

    def test_order_labels_are_what_is_held_for_that_order(self):
        self.reserve(self.fulfilment)
        codes = sorted(label["code"] for label in labels_for_order(self.order))

        held = ([unit.asset_id for unit in SerializedUnit.objects.filter(order=self.order)]
                + [lot.batch_id for lot in BatchLot.objects.filter(order=self.order)])
        self.assertTrue(held)
        self.assertEqual(codes, sorted(held))

    def test_the_sheet_is_a_pdf_four_labels_to_a_page(self):
        response = self.fetch(purchase_order=self.purchase.pk)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertIn(f"labels-{self.purchase.reference}.pdf", response["Content-Disposition"])
        expected = math.ceil(len(labels_for_purchase(self.purchase)) / LABELS_PER_PAGE)
        self.assertEqual(len(PAGE_OBJECT.findall(response.content)), expected)

    def test_a_purchase_order_or_an_order_is_required(self):
        self.assertEqual(self.fetch().status_code, 400)
        self.assertEqual(self.fetch(purchase_order=self.purchase.pk,
                                    order=self.order.pk).status_code, 400)

    def test_only_roles_that_see_stock_may_print(self):
        for user in (self.sales, self.technician):
            with self.subTest(user=user.username):
                self.assertEqual(self.fetch(user, purchase_order=self.purchase.pk).status_code, 403)
        self.client.logout()
        self.assertEqual(self.client.get(reverse("stock-labels"),
                                         {"purchase_order": self.purchase.pk}).status_code, 403)

    def test_invalid_identifiers_are_rejected(self):
        for field in ("purchase_order", "order"):
            for value in ("invalid", "0", "-1"):
                with self.subTest(field=field, value=value):
                    self.assertEqual(self.fetch(**{field: value}).status_code, 400)
