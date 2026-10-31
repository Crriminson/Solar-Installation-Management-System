"""
F12 - what warranties have to prove.

The expensive mistakes: a warranty that starts at the wrong moment, a
leap day that quietly shortens cover, a policy edit that rewrites what a
customer was promised, and a replacement that extends cover or loses the
failed unit's history.

Dates use real past days rather than a frozen clock, because delivery
refuses the future. Order confirmation is moved back to allow them.
"""

import threading
from datetime import date, datetime, timezone as utc
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, SimpleTestCase, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.accounts.models import Role
from apps.catalogue.models import Product, WarrantyPolicy
from apps.core.api import business_date
from apps.core.models import AuditEvent
from apps.fulfilment.models import FulfilmentStatus
from apps.fulfilment.tests import FulfilmentFixture
from apps.inventory.models import SerializedUnit, StockStatus
from apps.orders.models import Order

from .coverage import coverage_expiry
from .models import AssetWarranty, CoverageBasis, WarrantyStatus
from .services import issue_warranties, record_replacement

User = get_user_model()
JSON = "application/json"

PANEL_MONTHS = 240
EQUIPMENT_MONTHS = 24


def moment(year, month, day, hour=6, minute=0):
    return datetime(year, month, day, hour, minute, tzinfo=utc.utc)


class WarrantyFixture(FulfilmentFixture):
    """A deliverable order whose panels and inverters carry warranty policies."""

    def setUp(self):
        super().setUp()
        self.panel_policy = WarrantyPolicy.objects.create(
            name="Test panel", duration_months=PANEL_MONTHS, conditions="Panel terms."
        )
        self.equipment_policy = WarrantyPolicy.objects.create(
            name="Test equipment", duration_months=EQUIPMENT_MONTHS,
            conditions="Equipment terms.",
        )
        Product.objects.filter(sku="PANEL").update(warranty_policy=self.panel_policy)
        Product.objects.filter(sku="INV").update(warranty_policy=self.equipment_policy)

    def post_step(self, fulfilment, step, **body):
        """Sends one warehouse action with the revision currently on screen."""
        fulfilment.refresh_from_db()
        self.client.force_login(self.warehouse)
        return self.client.post(
            reverse(f"fulfilment-{step}", args=[fulfilment.pk]),
            {"revision": fulfilment.revision, **body}, content_type=JSON,
        )

    def dispatched(self):
        """Packed and on the van: everything short of delivery."""
        fulfilment = self.stock_everything()
        self.reserve(fulfilment)
        self.scan_everything(fulfilment)
        self.post_step(fulfilment, "close")
        self.post_step(fulfilment, "dispatch")
        return fulfilment

    def record_delivery(self, fulfilment, delivered_at=None):
        return self.post_step(
            fulfilment, "deliver",
            delivered_at=(delivered_at or timezone.now()).isoformat(),
            received_by_name="Ramesh Gupta",
        )

    def delivered(self, delivered_at=None):
        """A delivered order. Passing a past date backdates its confirmation."""
        if delivered_at is not None:
            Order.objects.filter(pk=self.order.pk).update(confirmed_at=moment(2020, 1, 1))
        fulfilment = self.dispatched()
        response = self.record_delivery(fulfilment, delivered_at)
        self.assertEqual(response.status_code, 200, response.content)
        return fulfilment

    def warranty_on(self, sku):
        return AssetWarranty.objects.filter(unit__product__sku=sku).first()

    def spare_unit(self, sku="INV", **fields):
        """A unit already issued to this customer, as F13 will leave it."""
        like = SerializedUnit.objects.filter(product__sku=sku).first()
        values = {"status": StockStatus.DELIVERED, "customer_id": self.order.customer_id,
                  "site_id": self.order.site_id, **fields}
        return SerializedUnit.objects.create(
            product=like.product, goods_receipt=like.goods_receipt,
            acquisition_cost="10.00", **values,
        )


class WarrantyTestCase(WarrantyFixture, TestCase):
    pass


# ============================================================
# Calendar arithmetic
# ============================================================

class ExpiryDateTests(SimpleTestCase):
    def test_an_ordinary_expiry_is_the_same_day_later(self):
        self.assertEqual(coverage_expiry(date(2027, 1, 15), 24), date(2029, 1, 15))

    def test_a_leap_day_start_moves_forward_when_the_day_does_not_exist(self):
        """D049: expiry is exclusive, so the 28th would lose a day of cover."""
        self.assertEqual(coverage_expiry(date(2028, 2, 29), 24), date(2030, 3, 1))

    def test_a_leap_day_start_keeps_its_day_when_the_expiry_year_is_leap(self):
        self.assertEqual(coverage_expiry(date(2028, 2, 29), 240), date(2048, 2, 29))

    def test_the_last_day_of_a_long_month_rolls_into_the_next(self):
        self.assertEqual(coverage_expiry(date(2027, 1, 31), 1), date(2027, 3, 1))

    def test_a_year_boundary_is_crossed_correctly(self):
        self.assertEqual(coverage_expiry(date(2026, 11, 30), 2), date(2027, 1, 30))
        self.assertEqual(coverage_expiry(date(2026, 12, 15), 12), date(2027, 12, 15))


# ============================================================
# Issuing on delivery
# ============================================================

class IssuingTests(WarrantyTestCase):
    def test_nothing_starts_at_packing_or_dispatch(self):
        """The clock starts when the customer has the equipment."""
        fulfilment = self.stock_everything()
        self.reserve(fulfilment)
        self.scan_everything(fulfilment)
        self.post_step(fulfilment, "close")
        self.assertFalse(AssetWarranty.objects.exists())

        self.post_step(fulfilment, "dispatch")
        self.assertFalse(AssetWarranty.objects.exists())

    def test_delivery_creates_one_warranty_per_eligible_unit(self):
        self.delivered()

        units = SerializedUnit.objects.filter(order=self.order)
        self.assertGreater(units.count(), 0)
        self.assertEqual(AssetWarranty.objects.count(), units.count())
        self.assertEqual(
            set(AssetWarranty.objects.values_list("unit_id", flat=True)),
            set(units.values_list("id", flat=True)),
        )

    def test_a_warranty_records_who_and_where(self):
        fulfilment = self.delivered()

        warranty = self.warranty_on("INV")
        self.assertEqual(warranty.customer_id, self.order.customer_id)
        self.assertEqual(warranty.site_id, self.order.site_id)
        self.assertEqual(warranty.order_id, self.order.pk)
        self.assertEqual(warranty.fulfilment_id, fulfilment.pk)
        self.assertEqual(warranty.coverage_basis, CoverageBasis.DELIVERY)
        self.assertEqual(warranty.created_by, self.warehouse)

    def test_bulk_stock_is_not_warranted_even_with_a_policy(self):
        """A metre of cable has no identity to attach a warranty to."""
        Product.objects.filter(sku="CABLE").update(warranty_policy=self.panel_policy)

        self.delivered()

        self.assertFalse(AssetWarranty.objects.filter(unit__product__sku="CABLE").exists())

    def test_a_unit_with_no_policy_is_reported_not_hidden(self):
        Product.objects.filter(sku="INV").update(warranty_policy=None)

        with self.assertLogs("apps.warranties.services", level="WARNING"):
            fulfilment = self.delivered()

        fulfilment.refresh_from_db()
        self.assertEqual(fulfilment.status, FulfilmentStatus.DELIVERED)
        inverter = SerializedUnit.objects.get(product__sku="INV", order=self.order)
        self.assertFalse(inverter.warranties.exists())

        event = AuditEvent.objects.get(action="warranties_issued")
        self.assertEqual(event.after["not_covered"], [inverter.asset_id])

        self.client.force_login(self.warehouse)
        body = self.client.get(reverse("order-warranties", args=[self.order.pk])).json()
        self.assertEqual([row["asset_id"] for row in body["uncovered_units"]],
                         [inverter.asset_id])

    def test_a_failed_issue_undoes_the_delivery(self):
        """A delivery with no cover behind it must not commit."""
        fulfilment = self.dispatched()

        with patch("apps.fulfilment.services.issue_warranties", side_effect=RuntimeError):
            with self.assertRaises(RuntimeError):
                self.record_delivery(fulfilment)

        fulfilment.refresh_from_db()
        self.order.refresh_from_db()
        self.assertEqual(fulfilment.status, FulfilmentStatus.DISPATCHED)
        self.assertIsNone(self.order.balance_due_on)
        self.assertTrue(SerializedUnit.objects.filter(
            order=self.order, status=StockStatus.DISPATCHED).exists())

    def test_recording_delivery_twice_leaves_one_set(self):
        fulfilment = self.delivered()
        count = AssetWarranty.objects.count()

        again = self.record_delivery(fulfilment)

        self.assertEqual(again.status_code, 400)
        self.assertEqual(AssetWarranty.objects.count(), count)

    def test_delivery_before_the_order_existed_is_refused(self):
        fulfilment = self.dispatched()

        response = self.record_delivery(fulfilment, moment(2020, 1, 1))

        self.assertEqual(response.status_code, 400)
        self.assertIn("before the order was confirmed", str(response.content))
        self.assertFalse(AssetWarranty.objects.exists())

    def test_units_still_on_the_van_are_not_called_uncovered(self):
        """Not covered means delivered without cover, not delivered yet."""
        self.dispatched()

        self.client.force_login(self.warehouse)
        body = self.client.get(reverse("order-warranties", args=[self.order.pk])).json()

        self.assertEqual(body, {"warranties": [], "uncovered_units": []})

    def test_the_audit_trail_records_each_warranty(self):
        self.delivered()

        warranty = self.warranty_on("INV")
        event = AuditEvent.objects.get(
            record_type="warranties.assetwarranty", record_id=warranty.pk)
        self.assertEqual(event.action, "issued")
        self.assertEqual(event.actor, self.warehouse)


# ============================================================
# Start and expiry on a real delivery
# ============================================================

class CoverageDateTests(WarrantyTestCase):
    def test_a_late_entry_uses_the_delivery_date_not_today(self):
        self.delivered(moment(2025, 6, 10))

        warranty = self.warranty_on("INV")
        self.assertNotEqual(warranty.coverage_start, business_date())
        self.assertEqual(warranty.coverage_start, date(2025, 6, 10))
        self.assertEqual(warranty.coverage_expires_on, date(2027, 6, 10))
        self.assertEqual(warranty.delivered_at, moment(2025, 6, 10))

    def test_a_delivery_after_midnight_in_india_uses_the_indian_date(self):
        """18:45 UTC on 28 Feb is 00:15 on 1 March in Asia/Kolkata."""
        self.delivered(moment(2026, 2, 28, 18, 45))

        warranty = self.warranty_on("INV")
        self.assertEqual(warranty.coverage_start, date(2026, 3, 1))
        self.assertEqual(warranty.coverage_expires_on, date(2028, 3, 1))

    def test_a_leap_day_delivery_through_the_whole_flow(self):
        self.delivered(moment(2024, 2, 29))

        inverter = self.warranty_on("INV")
        self.assertEqual(inverter.coverage_expires_on, date(2026, 3, 1))
        self.assertEqual(inverter.last_covered_on, date(2026, 2, 28))

        panel = self.warranty_on("PANEL")
        self.assertEqual(panel.coverage_expires_on, date(2044, 2, 29))
        self.assertEqual(panel.last_covered_on, date(2044, 2, 28))

    def test_each_product_gets_its_own_term(self):
        self.delivered()

        self.assertEqual(self.warranty_on("PANEL").duration_months, PANEL_MONTHS)
        self.assertEqual(self.warranty_on("INV").duration_months, EQUIPMENT_MONTHS)


class CoversTests(WarrantyTestCase):
    def setUp(self):
        super().setUp()
        self.delivered(moment(2025, 3, 10))
        self.warranty = self.warranty_on("INV")

    def test_the_first_day_is_covered(self):
        self.assertTrue(self.warranty.covers(date(2025, 3, 10)))

    def test_the_day_before_the_first_is_not(self):
        self.assertFalse(self.warranty.covers(date(2025, 3, 9)))

    def test_the_last_day_is_covered(self):
        self.assertTrue(self.warranty.covers(self.warranty.last_covered_on))

    def test_the_expiry_day_is_not(self):
        self.assertFalse(self.warranty.covers(self.warranty.coverage_expires_on))

    def test_cover_passes_to_the_replacement_on_the_swap_day(self):
        replacement = record_replacement(self.warranty.pk, self.spare_unit().pk, {
            "complaint_at": moment(2026, 1, 10), "replaced_at": moment(2026, 1, 20),
            "reason": "Inverter failed",
        }, self.warehouse)
        original = AssetWarranty.objects.get(pk=self.warranty.pk)

        self.assertTrue(original.covers(date(2026, 1, 19)))
        self.assertFalse(original.covers(date(2026, 1, 20)))
        self.assertTrue(replacement.covers(date(2026, 1, 20)))


# ============================================================
# Snapshots and policy versions
# ============================================================

class PolicySnapshotTests(WarrantyTestCase):
    def test_the_policy_is_copied_at_delivery(self):
        self.delivered()

        warranty = self.warranty_on("INV")
        self.assertEqual(warranty.policy_name, "Test equipment")
        self.assertEqual(warranty.policy_version, 1)
        self.assertEqual(warranty.conditions, "Equipment terms.")
        self.assertFalse(warranty.fresh_period_on_replacement)

    def test_changing_a_policy_never_rewrites_existing_cover(self):
        self.delivered()
        warranty = self.warranty_on("INV")
        expiry = warranty.coverage_expires_on

        self.equipment_policy.duration_months = 60
        self.equipment_policy.conditions = "Worse terms."
        self.equipment_policy.save()

        warranty = AssetWarranty.objects.get(pk=warranty.pk)
        self.assertEqual(warranty.coverage_expires_on, expiry)
        self.assertEqual(warranty.duration_months, EQUIPMENT_MONTHS)
        self.assertEqual(warranty.conditions, "Equipment terms.")
        self.assertEqual(warranty.policy_version, 1)

    def test_the_policy_that_counts_is_the_one_at_delivery_not_at_quotation(self):
        """This order was quoted before the change and delivered after it."""
        self.equipment_policy.duration_months = 36
        self.equipment_policy.save()

        self.delivered()

        warranty = self.warranty_on("INV")
        self.assertEqual(warranty.policy_version, 2)
        self.assertEqual(warranty.duration_months, 36)

    def test_changing_terms_makes_a_new_version(self):
        for field, value in [("duration_months", 30), ("conditions", "New."),
                             ("fresh_period_on_replacement", True)]:
            before = self.equipment_policy.version
            setattr(self.equipment_policy, field, value)
            self.equipment_policy.save()
            self.assertEqual(self.equipment_policy.version, before + 1, field)

    def test_renaming_a_policy_is_not_a_new_version(self):
        self.equipment_policy.name = "Renamed"
        self.equipment_policy.save()

        self.assertEqual(self.equipment_policy.version, 1)

    def test_a_stale_copy_cannot_skip_a_version(self):
        stale = WarrantyPolicy.objects.get(pk=self.equipment_policy.pk)
        self.equipment_policy.duration_months = 30
        self.equipment_policy.save()

        stale.name = "Renamed"
        stale.duration_months = 30
        stale.save()

        self.assertEqual(WarrantyPolicy.objects.get(pk=stale.pk).version, 2)

    def test_a_policy_with_no_term_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            WarrantyPolicy.objects.filter(pk=self.equipment_policy.pk).update(duration_months=0)

    def test_an_admin_revision_keeps_the_old_terms_in_the_audit_trail(self):
        admin_user = User.objects.create_superuser("war_super", password="unused")
        self.client.force_login(admin_user)

        response = self.client.post(
            reverse("admin:catalogue_warrantypolicy_change",
                    args=[self.equipment_policy.pk]),
            {"name": "Test equipment", "duration_months": 36, "conditions": "New terms."},
        )

        self.assertEqual(response.status_code, 302, response.content)
        event = AuditEvent.objects.get(action="revised")
        self.assertEqual(event.actor, admin_user)
        self.assertEqual(event.before["duration_months"], EQUIPMENT_MONTHS)
        self.assertEqual(event.after["duration_months"], 36)
        self.assertEqual(event.after["version"], 2)


# ============================================================
# Replacement
# ============================================================

class ReplacementTestCase(WarrantyTestCase):
    def setUp(self):
        super().setUp()
        self.delivered(moment(2025, 3, 10))
        self.original = self.warranty_on("INV")

    def replace(self, warranty=None, unit=None, **changes):
        data = {"complaint_at": moment(2026, 1, 10), "replaced_at": moment(2026, 1, 20),
                "reason": "Inverter failed", **changes}
        return record_replacement((warranty or self.original).pk,
                                  (unit or self.spare_unit()).pk, data, self.warehouse)

    def reloaded(self, warranty):
        return AssetWarranty.objects.get(pk=warranty.pk)


class ReplacementCoverageTests(ReplacementTestCase):
    def test_a_replacement_inherits_the_remaining_cover(self):
        replacement = self.replace()

        self.assertEqual(replacement.coverage_basis, CoverageBasis.INHERITED)
        self.assertEqual(replacement.coverage_start, date(2026, 1, 20))
        self.assertEqual(replacement.coverage_expires_on,
                         self.original.coverage_expires_on)

    def test_a_replacement_keeps_the_original_terms(self):
        replacement = self.replace()

        self.assertEqual(replacement.policy_name, self.original.policy_name)
        self.assertEqual(replacement.policy_version, self.original.policy_version)
        self.assertEqual(replacement.conditions, self.original.conditions)
        self.assertEqual(replacement.customer_id, self.original.customer_id)
        self.assertEqual(replacement.order_id, self.original.order_id)

    def test_a_fresh_period_is_granted_only_when_the_snapshot_says_so(self):
        AssetWarranty.objects.filter(pk=self.original.pk).update(
            fresh_period_on_replacement=True)

        replacement = self.replace(self.reloaded(self.original))

        self.assertEqual(replacement.coverage_basis, CoverageBasis.FRESH)
        self.assertEqual(replacement.coverage_start, date(2026, 1, 20))
        self.assertEqual(replacement.coverage_expires_on, date(2028, 1, 20))

    def test_a_later_policy_change_cannot_grant_a_fresh_period(self):
        self.equipment_policy.fresh_period_on_replacement = True
        self.equipment_policy.save()

        replacement = self.replace()

        self.assertEqual(replacement.coverage_basis, CoverageBasis.INHERITED)
        self.assertEqual(replacement.policy_version, 1)

    def test_replacing_twice_never_extends_cover(self):
        first = self.replace()

        second = self.replace(first, replaced_at=moment(2026, 6, 1),
                              complaint_at=moment(2026, 5, 20))

        self.assertEqual(second.coverage_start, date(2026, 6, 1))
        self.assertEqual(second.coverage_expires_on, self.original.coverage_expires_on)

    def test_a_replacement_after_expiry_keeps_the_link_but_adds_no_cover(self):
        """D021 honours the claim. D050 refuses to invent cover nobody sold."""
        AssetWarranty.objects.filter(pk=self.original.pk).update(
            coverage_start=date(2024, 3, 10), coverage_expires_on=date(2026, 3, 10))

        replacement = self.replace(
            self.reloaded(self.original),
            complaint_at=moment(2026, 3, 5), replaced_at=moment(2026, 3, 15),
        )

        self.assertEqual(replacement.coverage_start, date(2026, 3, 10))
        self.assertEqual(replacement.coverage_expires_on, date(2026, 3, 10))
        self.assertIsNone(replacement.last_covered_on)
        self.assertEqual(replacement.status, WarrantyStatus.EXPIRED)
        self.assertEqual(replacement.replaces_id, self.original.pk)

    def test_a_late_visit_does_not_lose_a_valid_claim(self):
        """Judged on the complaint: the swap itself falls after expiry."""
        AssetWarranty.objects.filter(pk=self.original.pk).update(
            coverage_start=date(2024, 3, 10), coverage_expires_on=date(2026, 3, 10))

        self.replace(self.reloaded(self.original),
                     complaint_at=moment(2026, 3, 9), replaced_at=moment(2026, 5, 1))

        self.assertTrue(self.reloaded(self.original).is_replaced)


class ReplacementHistoryTests(ReplacementTestCase):
    def test_the_failed_units_record_is_left_exactly_as_it_was(self):
        before = AssetWarranty.objects.filter(pk=self.original.pk).values().get()

        self.replace()

        after = AssetWarranty.objects.filter(pk=self.original.pk).values().get()
        self.assertEqual(after, before)

    def test_both_serials_are_linked_from_either_end(self):
        spare = self.spare_unit(serial_number="SPARE-1")
        replacement = self.replace(unit=spare)
        expected = [self.original.unit.asset_id, spare.asset_id]

        self.client.force_login(self.warehouse)
        for warranty in (self.original, replacement):
            body = self.client.get(reverse("warranty-detail", args=[warranty.pk])).json()
            self.assertEqual([row["asset_id"] for row in body["history"]], expected)

    def test_a_replaced_unit_stops_being_covered_the_day_before_the_swap(self):
        """The record must not promise cover that has moved to another unit."""
        self.replace()

        original = self.reloaded(self.original)
        self.assertEqual(original.last_covered_on, date(2026, 1, 19))
        self.assertEqual(original.coverage_expires_on, date(2027, 3, 10))

    def test_a_unit_replaced_on_its_first_day_has_no_covered_day(self):
        self.replace(complaint_at=moment(2025, 3, 10), replaced_at=moment(2025, 3, 10))

        self.assertIsNone(self.reloaded(self.original).last_covered_on)

    def test_the_original_shows_as_replaced(self):
        replacement = self.replace()

        original = self.reloaded(self.original)
        self.assertEqual(original.status, WarrantyStatus.REPLACED)
        self.assertEqual(original.replaced_by, replacement)

    def test_a_replacement_carries_its_reason(self):
        replacement = self.replace(reason="  Burnt board  ")

        self.assertEqual(replacement.replacement_reason, "Burnt board")
        self.assertTrue(AuditEvent.objects.filter(
            action="replaced", record_id=self.original.pk, reason="Burnt board").exists())

    def test_a_replacement_has_no_delivery_of_its_own(self):
        self.assertIsNone(self.replace().fulfilment_id)


class ReplacementRefusalTests(ReplacementTestCase):
    def assert_refused(self, field, **kwargs):
        with self.assertRaises(ValidationError) as caught:
            self.replace(**kwargs)
        self.assertIn(field, caught.exception.detail)

    def test_a_warranty_is_replaced_only_once(self):
        self.replace()

        self.assert_refused("warranty", warranty=self.reloaded(self.original))

    def test_a_unit_cannot_replace_itself(self):
        self.assert_refused("unit", unit=self.original.unit)

    def test_a_unit_still_in_the_warehouse_is_refused(self):
        self.assert_refused("unit", unit=self.spare_unit(
            status=StockStatus.AVAILABLE, customer_id=None, site_id=None))

    def test_a_unit_delivered_to_someone_else_is_refused(self):
        other = self.order.customer.__class__.objects.create(
            full_name="Someone Else", phone="9000000000")

        self.assert_refused("unit", unit=self.spare_unit(customer_id=other.pk))

    def test_a_unit_already_in_cover_is_refused(self):
        self.assert_refused("unit", unit=self.warranty_on("PANEL").unit)

    def test_a_replacement_in_the_future_is_refused(self):
        self.assert_refused("replaced_at", replaced_at=moment(2099, 1, 1))

    def test_a_replacement_before_the_warranty_started_is_refused(self):
        self.assert_refused("replaced_at", replaced_at=moment(2025, 3, 1),
                            complaint_at=moment(2025, 2, 20))

    def test_a_complaint_after_the_replacement_is_refused(self):
        self.assert_refused("complaint_at", complaint_at=moment(2026, 2, 1))

    def test_a_complaint_outside_cover_is_sent_to_review(self):
        AssetWarranty.objects.filter(pk=self.original.pk).update(
            coverage_start=date(2024, 3, 10), coverage_expires_on=date(2026, 1, 1))

        self.assert_refused("complaint_at", warranty=self.reloaded(self.original))

    def test_a_replacement_needs_a_reason(self):
        self.assert_refused("reason", reason="   ")


# ============================================================
# Database and model guards
# ============================================================

class ImmutabilityTests(WarrantyTestCase):
    def setUp(self):
        super().setUp()
        self.delivered()
        self.warranty = self.warranty_on("INV")

    def copy_of(self, **changes):
        """A new row like the existing one, with the unit swapped by default."""
        fields = {"unit": self.warranty_on("PANEL").unit, "customer": self.warranty.customer,
                  "site": self.warranty.site, "order": self.warranty.order,
                  "fulfilment": self.warranty.fulfilment,
                  "delivered_at": self.warranty.delivered_at, "policy": self.warranty.policy,
                  "policy_name": "Copy", "policy_version": 1, "duration_months": 24,
                  "fresh_period_on_replacement": False, "coverage_basis": "delivery",
                  "coverage_start": date(2026, 1, 1),
                  "coverage_expires_on": date(2028, 1, 1), "created_by": self.warehouse}
        return AssetWarranty(**{**fields, **changes})

    def assert_refused_by_database(self, **changes):
        with self.assertRaises(IntegrityError), transaction.atomic():
            self.copy_of(**changes).save()

    def test_a_warranty_cannot_be_edited(self):
        self.warranty.coverage_expires_on = date(2099, 1, 1)

        with self.assertRaises(ModelValidationError):
            self.warranty.save()

    def test_a_warranty_cannot_be_deleted(self):
        with self.assertRaises(ModelValidationError):
            self.warranty.delete()

    def test_one_delivery_cannot_warrant_a_unit_twice(self):
        self.assert_refused_by_database(unit=self.warranty.unit)

    def test_a_window_cannot_run_backwards(self):
        self.assert_refused_by_database(coverage_expires_on=date(2025, 1, 1))

    def test_a_warranty_needs_a_term(self):
        self.assert_refused_by_database(duration_months=0)

    def test_a_warranty_needs_an_origin(self):
        self.assert_refused_by_database(fulfilment=None)

    def test_a_replacement_needs_a_reason_in_the_database_too(self):
        self.assert_refused_by_database(
            fulfilment=None, replaces=self.warranty, coverage_basis="inherited")

    def test_a_warranty_is_replaced_once_in_the_database_too(self):
        self.copy_of(fulfilment=None, replaces=self.warranty, coverage_basis="inherited",
                     replacement_reason="Failed", unit=self.warranty.unit).save()

        self.assert_refused_by_database(
            fulfilment=None, replaces=self.warranty, coverage_basis="inherited",
            replacement_reason="Failed again")


# ============================================================
# API
# ============================================================

class WarrantyApiTests(WarrantyTestCase):
    def setUp(self):
        super().setUp()
        # Inverter cover from 2024 has run out; the 20-year panels have not.
        self.delivered(moment(2024, 3, 10))
        self.inverter = self.warranty_on("INV")
        self.client.force_login(self.warehouse)

    def listed(self, **params):
        response = self.client.get(reverse("warranty-list"), params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["results"]

    def test_search_finds_a_warranty_by_every_identity(self):
        unit = self.inverter.unit
        SerializedUnit.objects.filter(pk=unit.pk).update(serial_number="MFR-XYZ-123")

        for term in ["MFR-XYZ", unit.asset_id, "Quote Customer", "9876543210",
                     self.order.reference]:
            self.assertIn(self.inverter.pk, [row["id"] for row in self.listed(search=term)],
                          term)

    def test_search_excludes_what_does_not_match(self):
        self.assertEqual(self.listed(search="NOBODY"), [])

    def test_the_status_filter_uses_todays_date(self):
        expired = [row["id"] for row in self.listed(status="expired")]
        in_cover = [row["id"] for row in self.listed(status="in_cover")]

        self.assertEqual(expired, [self.inverter.pk])
        self.assertIn(self.warranty_on("PANEL").pk, in_cover)
        self.assertNotIn(self.inverter.pk, in_cover)
        self.assertEqual(self.listed(status="replaced"), [])

    def test_a_replaced_warranty_leaves_the_other_filters(self):
        """The inverter expired too, but Replaced is the fact that matters."""
        spare = self.spare_unit()
        record_replacement(self.inverter.pk, spare.pk, {
            "complaint_at": moment(2026, 1, 10), "replaced_at": moment(2026, 1, 20),
            "reason": "Inverter failed",
        }, self.warehouse)

        self.assertEqual([row["id"] for row in self.listed(status="replaced")],
                         [self.inverter.pk])
        self.assertNotIn(self.inverter.pk, [row["id"] for row in self.listed(status="expired")])

    def test_a_row_reports_its_status_and_last_covered_day(self):
        row = next(row for row in self.listed() if row["id"] == self.inverter.pk)

        self.assertEqual(row["status"], "expired")
        self.assertEqual(row["coverage_expires_on"], "2026-03-10")
        self.assertEqual(row["last_covered_on"], "2026-03-09")

    def test_filters_narrow_to_an_order_and_a_customer(self):
        self.assertEqual(len(self.listed(order=self.order.pk)), AssetWarranty.objects.count())
        self.assertEqual(self.listed(order=self.order.pk + 999), [])
        self.assertEqual(self.listed(customer=self.order.customer_id + 999), [])

    def test_a_bad_filter_is_refused_by_name(self):
        for params, field in [({"status": "nonsense"}, "status"), ({"order": "abc"}, "order"),
                              ({"customer": "abc"}, "customer")]:
            response = self.client.get(reverse("warranty-list"), params)
            self.assertEqual(response.status_code, 400, params)
            self.assertIn(field, response.json())

    def test_the_record_shows_the_policy_terms(self):
        body = self.client.get(reverse("warranty-detail", args=[self.inverter.pk])).json()

        self.assertEqual(body["conditions"], "Equipment terms.")
        self.assertEqual(body["policy_version"], 1)
        self.assertEqual(body["duration_months"], EQUIPMENT_MONTHS)
        self.assertEqual(len(body["history"]), 1)

    def test_an_unknown_warranty_or_order_is_a_404(self):
        self.assertEqual(
            self.client.get(reverse("warranty-detail", args=[999999])).status_code, 404)
        self.assertEqual(
            self.client.get(reverse("order-warranties", args=[999999])).status_code, 404)

    def test_the_order_view_lists_all_of_its_cover(self):
        body = self.client.get(reverse("order-warranties", args=[self.order.pk])).json()

        self.assertEqual(len(body["warranties"]), AssetWarranty.objects.count())
        self.assertEqual(body["uncovered_units"], [])

    def test_acquisition_cost_never_reaches_a_payload(self):
        for url in [reverse("warranty-list"),
                    reverse("warranty-detail", args=[self.inverter.pk]),
                    reverse("order-warranties", args=[self.order.pk])]:
            self.assertNotIn("acquisition_cost", str(self.client.get(url).content))

    def test_the_list_does_not_run_a_query_per_row(self):
        with CaptureQueriesContext(connection) as one_row:
            self.client.get(reverse("warranty-list"), {"page_size": 1})
        with CaptureQueriesContext(connection) as all_rows:
            self.client.get(reverse("warranty-list"))

        self.assertGreater(AssetWarranty.objects.count(), 1)
        self.assertEqual(len(one_row), len(all_rows))


class WarrantyPermissionTests(WarrantyTestCase):
    READERS = [Role.SUPPORT, Role.OPERATIONS_MANAGER, Role.SALES, Role.WAREHOUSE,
               Role.FINANCE, Role.DIRECTOR, Role.ADMINISTRATOR]

    def setUp(self):
        super().setUp()
        self.delivered()
        warranty = self.warranty_on("INV")
        self.urls = [reverse("warranty-list"),
                     reverse("warranty-detail", args=[warranty.pk]),
                     reverse("order-warranties", args=[self.order.pk])]

    def login_as(self, role):
        self.client.force_login(User.objects.create_user(f"war_{role}", roles=[role]))

    def test_every_reading_role_can_read(self):
        for role in self.READERS:
            self.login_as(role)
            for url in self.urls:
                self.assertEqual(self.client.get(url).status_code, 200, f"{role} {url}")

    def test_a_technician_is_refused(self):
        self.login_as(Role.TECHNICIAN)

        for url in self.urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_someone_not_signed_in_is_refused(self):
        self.client.logout()

        for url in self.urls:
            self.assertEqual(self.client.get(url).status_code, 403, url)

    def test_a_former_staff_member_is_refused(self):
        user = User.objects.create_user("war_left", roles=[Role.SUPPORT],
                                        is_active_staff=False)
        self.client.force_login(user)

        self.assertEqual(self.client.get(self.urls[0]).status_code, 403)

    def test_nobody_writes_here_not_even_an_administrator(self):
        """Warranties come from events. There is no form to fill in."""
        self.login_as(Role.ADMINISTRATOR)

        for url in self.urls:
            for method in (self.client.post, self.client.put, self.client.delete):
                self.assertEqual(method(url, {}, content_type=JSON).status_code, 403, url)


# ============================================================
# Concurrency, with real threads
# ============================================================

class SimultaneousWarrantyTests(WarrantyFixture, TransactionTestCase):
    def run_together(self, work, count=2):
        """Runs work(index) on threads released at the same moment."""
        barrier = threading.Barrier(count)

        def run(index):
            try:
                work(index, barrier)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=run, args=[index]) for index in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def test_two_people_recording_one_delivery_issue_one_set(self):
        fulfilment = self.dispatched()
        fulfilment.refresh_from_db()
        codes = []

        def deliver(_index, barrier):
            client = Client(raise_request_exception=False)
            client.force_login(self.warehouse)
            barrier.wait()
            codes.append(client.post(
                reverse("fulfilment-deliver", args=[fulfilment.pk]),
                {"revision": fulfilment.revision, "received_by_name": "Ramesh Gupta",
                 "delivered_at": timezone.now().isoformat()},
                content_type=JSON,
            ).status_code)

        self.run_together(deliver)

        self.assertEqual(sorted(codes), [200, 409])
        self.assertEqual(AssetWarranty.objects.count(),
                         SerializedUnit.objects.filter(order=self.order).count())

    def test_two_replacements_of_one_warranty_have_one_winner(self):
        self.delivered()
        original = AssetWarranty.objects.filter(unit__product__sku="INV").get()
        spares = [self.spare_unit(), self.spare_unit()]
        outcomes = []

        def replace(index, barrier):
            barrier.wait()
            now = timezone.now()
            try:
                record_replacement(original.pk, spares[index].pk, {
                    "complaint_at": now, "replaced_at": now, "reason": "Failed",
                }, self.warehouse)
                outcomes.append("replaced")
            except ValidationError:
                outcomes.append("refused")

        self.run_together(replace)

        self.assertEqual(sorted(outcomes), ["refused", "replaced"])
        self.assertEqual(AssetWarranty.objects.filter(replaces=original).count(), 1)


# ============================================================
# Direct service use
# ============================================================

class IssueWarrantiesServiceTests(WarrantyTestCase):
    def test_issuing_again_cannot_duplicate_cover(self):
        """The unique constraint is the backstop behind the delivery lock."""
        fulfilment = self.delivered()

        with self.assertRaises(IntegrityError), transaction.atomic():
            issue_warranties(fulfilment, self.warehouse)
