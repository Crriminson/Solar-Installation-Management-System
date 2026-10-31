"""
Tests for F04 — catalogue, packages and component rules.

The rules worth proving: cost never reaches someone it is hidden from,
a reviewed version cannot change, a package cannot go live incomplete,
one version is active at a time, and quantities come out right.
"""

import threading
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role

from .models import (
    Category,
    PackageKind,
    PackageLine,
    PackageTemplate,
    Product,
    ProductPrice,
    QuantityBasis,
    SizingDefaults,
    TrackingMethod,
    VersionStatus,
)
from .sizing import (
    SizingError,
    battery_quantity,
    cable_quantity,
    parts_list,
    round_up_to_stocking_unit,
)

User = get_user_model()

JSON = "application/json"
PASSWORD = "test-pass-123"


def make_user(username, *roles):
    return User.objects.create_user(username, password=PASSWORD, roles=list(roles))


def make_product(sku, category=Category.OTHER, price="100.00", **overrides):
    fields = {
        "name": sku,
        "category": category,
        "tracking_method": TrackingMethod.BULK,
        "unit": "piece",
        "gst_rate_percent": "12.00",
        **overrides,
    }
    product = Product.objects.create(sku=sku, **fields)

    if price:
        # No password: hashing one per product makes the suite crawl.
        author, _ = User.objects.get_or_create(username="pricer")
        ProductPrice.objects.create(
            product=product,
            selling_price_excl_tax=price,
            purchase_cost_excl_tax="60.00",
            effective_from=timezone.localdate(),
            created_by=author,
        )
    return product


def add_line(version, product, quantity="1", basis=QuantityBasis.FIXED):
    is_fixed = basis == QuantityBasis.FIXED
    return PackageLine.objects.create(
        version=version, product=product, basis=basis,
        quantity=quantity if is_fixed else None,
    )


def make_complete_on_grid(creator):
    """A version holding every category an on-grid package needs."""
    template = PackageTemplate.objects.create(
        kind=PackageKind.ON_GRID, capacity_kw="3.00", name="On-Grid 3 kW"
    )
    version = template.start_new_version(creator)

    add_line(version, make_product("PANEL", Category.PANEL), "6")
    add_line(version, make_product("INV", Category.INVERTER))
    add_line(version, make_product("RAIL", Category.MOUNTING), "4")
    add_line(version, make_product("CONN", Category.CONNECTOR), "8")
    add_line(version, make_product("MCB", Category.PROTECTION))
    add_line(version, make_product("EARTH", Category.EARTHING))
    add_line(version, make_product("LABOUR", Category.SERVICE, unit="job"))
    add_line(
        version, make_product("CABLE", Category.CABLE, unit="m"),
        basis=QuantityBasis.CABLE_ROUTE,
    )
    return version


class CatalogueTestCase(TestCase):
    def setUp(self):
        self.manager = make_user("mgr", Role.OPERATIONS_MANAGER)
        self.admin = make_user("admin", Role.ADMINISTRATOR)
        self.sales = make_user("sales", Role.SALES)
        self.client.login(username="mgr", password=PASSWORD)

    def sign_in(self, username):
        self.client.logout()
        self.client.login(username=username, password=PASSWORD)


# ============================================================
# Sizing
# ============================================================

class SizingTests(TestCase):
    def setUp(self):
        self.version = SimpleNamespace(
            cable_waste_factor=Decimal("1.15"),
            cable_termination_buffer_m=Decimal("5"),
            battery_depth_of_discharge=Decimal("0.80"),
        )

    def test_cable_uses_the_waste_factor_and_buffer(self):
        cable = SimpleNamespace(stocking_quantity=Decimal("1"))

        self.assertEqual(cable_quantity(Decimal("20"), self.version, cable), Decimal("28"))

    def test_cable_rounds_up_to_the_stocking_unit(self):
        cable = SimpleNamespace(stocking_quantity=Decimal("5"))

        # 22.5 × 1.15 + 5 = 30.875 m, stocked in 5 m lengths.
        self.assertEqual(cable_quantity(Decimal("22.5"), self.version, cable), Decimal("35"))

    def test_an_exact_multiple_is_not_rounded_further(self):
        self.assertEqual(round_up_to_stocking_unit(Decimal("10"), Decimal("5")), Decimal("10"))

    def test_batteries_round_up_to_a_whole_unit(self):
        battery = SimpleNamespace(storage_kwh=Decimal("2.4"))

        # 1.5 kW × 6 h = 9 kWh, at 1.92 usable kWh each.
        self.assertEqual(
            battery_quantity(Decimal("1.5"), Decimal("6"), self.version, battery),
            Decimal("5"),
        )


class PartsListTests(TestCase):
    def setUp(self):
        self.creator = make_user("creator")
        self.template = PackageTemplate.objects.create(
            kind=PackageKind.OFF_GRID, capacity_kw="3.00", name="Off-Grid 3 kW"
        )
        self.version = self.template.start_new_version(self.creator)
        self.version.battery_depth_of_discharge = Decimal("0.80")
        self.version.save()

    def test_fixed_and_cable_lines_are_resolved_from_the_survey(self):
        panel = make_product("PANEL", Category.PANEL)
        cable = make_product("CABLE", Category.CABLE)
        add_line(self.version, panel, "6")
        add_line(self.version, cable, basis=QuantityBasis.CABLE_ROUTE)

        lines = parts_list(self.version, SimpleNamespace(cable_distance_m=Decimal("20")))

        quantities = {line.product.sku: line.quantity for line in lines}
        self.assertEqual(quantities, {"PANEL": Decimal("6"), "CABLE": Decimal("28")})

    def test_a_battery_line_names_what_the_survey_is_missing(self):
        """Blocked with a reason, never inferred from panel capacity."""
        battery = make_product("BATT", Category.BATTERY, storage_kwh="2.40")
        add_line(self.version, battery, basis=QuantityBasis.BATTERY_LOAD)
        revision = SimpleNamespace(critical_load_kw=None, backup_duration_hours=None)

        with self.assertRaises(SizingError) as caught:
            parts_list(self.version, revision)

        self.assertIn("critical load", str(caught.exception))


# ============================================================
# Costs and permissions
# ============================================================

class CostVisibilityTests(CatalogueTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product("PANEL", Category.PANEL)

    def fetch(self):
        return self.client.get(reverse("product-detail", args=[self.product.id])).content

    def test_sales_never_receives_the_purchase_cost(self):
        self.sign_in("sales")

        self.assertNotIn(b"purchase_cost_excl_tax", self.fetch())

    def test_sales_cannot_find_the_cost_in_the_list_either(self):
        self.sign_in("sales")

        response = self.client.get(reverse("product-list"))

        self.assertNotIn(b"purchase_cost_excl_tax", response.content)

    def test_finance_and_the_director_can_see_it(self):
        for username, role in [("fin", Role.FINANCE), ("dir", Role.DIRECTOR)]:
            make_user(username, role)
            self.sign_in(username)

            self.assertIn(b"purchase_cost_excl_tax", self.fetch())


class WritePermissionTests(CatalogueTestCase):
    def test_reading_requires_login(self):
        self.client.logout()

        self.assertIn(self.client.get(reverse("product-list")).status_code, [401, 403])

    def test_sales_can_read_but_not_write(self):
        self.sign_in("sales")

        self.assertEqual(self.client.get(reverse("product-list")).status_code, 200)
        response = self.client.post(
            reverse("product-list"),
            {
                "sku": "X", "name": "X", "category": "other", "unit": "piece",
                "tracking_method": "bulk", "gst_rate_percent": "12.00",
            },
            content_type=JSON,
        )
        self.assertEqual(response.status_code, 403)

    def test_an_operations_manager_cannot_take_a_package_live(self):
        version = make_complete_on_grid(self.manager)

        response = self.client.post(reverse("version-activate", args=[version.id]))

        self.assertEqual(response.status_code, 403)
        version.refresh_from_db()
        self.assertEqual(version.status, VersionStatus.DRAFT)

    def test_sales_cannot_change_a_price(self):
        product = make_product("PANEL", Category.PANEL)
        self.sign_in("sales")

        response = self.client.post(
            reverse("product-prices", args=[product.id]),
            {
                "selling_price_excl_tax": "1.00",
                "effective_from": timezone.localdate().isoformat(),
            },
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 403)


# ============================================================
# Prices
# ============================================================

class PriceTests(CatalogueTestCase):
    def setUp(self):
        super().setUp()
        self.product = make_product("PANEL", Category.PANEL, price=None)
        self.url = reverse("product-prices", args=[self.product.id])

    def add_price(self, amount, days_from_today=0):
        return self.client.post(
            self.url,
            {
                "selling_price_excl_tax": amount,
                "effective_from": (
                    timezone.localdate() + timedelta(days=days_from_today)
                ).isoformat(),
            },
            content_type=JSON,
        )

    def test_a_new_price_applies_from_its_date(self):
        self.add_price("100.00")
        self.add_price("150.00", days_from_today=7)

        product = Product.objects.get(pk=self.product.pk)
        self.assertEqual(product.current_price().selling_price_excl_tax, Decimal("100.00"))

    def test_the_price_history_is_kept(self):
        self.add_price("100.00")
        self.add_price("150.00", days_from_today=7)

        self.assertEqual(self.product.prices.count(), 2)

    def test_a_price_cannot_start_in_the_past(self):
        self.assertEqual(self.add_price("100.00", days_from_today=-1).status_code, 400)

    def test_two_prices_cannot_start_on_one_date(self):
        self.add_price("100.00")

        response = self.add_price("120.00")

        self.assertEqual(response.status_code, 400)
        self.assertIn("effective_from", response.json())


# ============================================================
# Package versions
# ============================================================

class VersionTests(CatalogueTestCase):
    def test_the_first_version_starts_from_the_configured_defaults(self):
        """Seeded as data, because spec.md section 14 forbids constants."""
        defaults = SizingDefaults.objects.get()
        template = PackageTemplate.objects.create(
            kind=PackageKind.PANEL_SET, name="Panel set"
        )

        version = template.start_new_version(self.manager)

        self.assertEqual(version.cable_waste_factor, defaults.cable_waste_factor)
        self.assertEqual(defaults.cable_waste_factor, Decimal("1.15"))
        self.assertEqual(defaults.cable_termination_buffer_m, Decimal("5.00"))

    def test_a_system_package_needs_a_capacity(self):
        response = self.client.post(
            reverse("package-list"),
            {"kind": "on_grid", "name": "No size"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 400)

    def test_a_package_cannot_go_live_with_required_parts_missing(self):
        template = PackageTemplate.objects.create(
            kind=PackageKind.ON_GRID, capacity_kw="3.00", name="On-Grid 3 kW"
        )
        version = template.start_new_version(self.manager)
        add_line(version, make_product("PANEL", Category.PANEL), "6")

        with self.assertRaises(ValidationError) as caught:
            version.activate(self.admin)

        self.assertIn("Missing a line for: Inverter.", caught.exception.messages)

    def test_a_product_with_no_price_blocks_going_live(self):
        version = make_complete_on_grid(self.manager)
        add_line(version, make_product("NOPRICE", price=None))

        with self.assertRaises(ValidationError) as caught:
            version.activate(self.admin)

        self.assertIn("NOPRICE has no selling price.", caught.exception.messages)

    def test_a_complete_version_goes_live_through_the_api(self):
        version = make_complete_on_grid(self.manager)
        self.sign_in("admin")

        response = self.client.post(reverse("version-activate", args=[version.id]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "active")

    def test_a_refusal_lists_every_problem_at_once(self):
        template = PackageTemplate.objects.create(
            kind=PackageKind.ON_GRID, capacity_kw="3.00", name="On-Grid 3 kW"
        )
        version = template.start_new_version(self.manager)
        add_line(version, make_product("PANEL", Category.PANEL), "6")
        self.sign_in("admin")

        response = self.client.post(reverse("version-activate", args=[version.id]))

        self.assertEqual(response.status_code, 400)
        self.assertGreater(len(response.json()["problems"]), 1)

    def test_a_new_version_copies_lines_and_figures(self):
        version = make_complete_on_grid(self.manager)
        version.activate(self.admin)

        draft = version.template.start_new_version(self.manager)

        self.assertEqual(draft.version_number, 2)
        self.assertEqual(draft.lines.count(), version.lines.count())

    def test_a_template_has_one_draft_at_a_time(self):
        version = make_complete_on_grid(self.manager)

        with self.assertRaises(ValidationError):
            version.template.start_new_version(self.manager)

    def test_going_live_retires_the_version_before(self):
        version = make_complete_on_grid(self.manager)
        version.activate(self.admin)
        draft = version.template.start_new_version(self.manager)

        draft.activate(self.admin)

        version.refresh_from_db()
        self.assertEqual(version.status, VersionStatus.RETIRED)
        self.assertEqual(draft.template.active_version, draft)

    def test_the_database_refuses_two_active_versions(self):
        version = make_complete_on_grid(self.manager)
        version.activate(self.admin)
        draft = version.template.start_new_version(self.manager)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                type(draft).objects.filter(pk=draft.pk).update(status=VersionStatus.ACTIVE)


class ReviewedVersionImmutabilityTests(CatalogueTestCase):
    def setUp(self):
        super().setUp()
        self.version = make_complete_on_grid(self.manager)
        self.version.activate(self.admin)

    def test_figures_cannot_change(self):
        self.version.cable_waste_factor = Decimal("2.00")

        with self.assertRaises(ValidationError):
            self.version.save()

    def test_setting_it_back_to_draft_does_not_unlock_it(self):
        """The check reads the database, not the copy being saved."""
        self.version.status = VersionStatus.DRAFT
        self.version.cable_waste_factor = Decimal("2.00")

        with self.assertRaises(ValidationError):
            self.version.save()

    def test_a_line_cannot_be_changed_or_removed(self):
        line = self.version.lines.first()
        line.quantity = Decimal("99")

        with self.assertRaises(ValidationError):
            line.save()
        with self.assertRaises(ValidationError):
            line.delete()

    def test_the_api_refuses_an_edit_with_a_plain_message(self):
        response = self.client.patch(
            reverse("version-detail", args=[self.version.id]),
            {"cable_waste_factor": "2.00"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("cannot be edited", response.json()["detail"])

    def test_the_api_refuses_a_new_line(self):
        response = self.client.post(
            reverse("line-create", args=[self.version.id]),
            {"product": make_product("EXTRA").id, "quantity": "1"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 400)


class DraftEditingTests(CatalogueTestCase):
    def test_a_calculated_line_stores_no_typed_quantity(self):
        template = PackageTemplate.objects.create(
            kind=PackageKind.ON_GRID, capacity_kw="1.00", name="On-Grid 1 kW"
        )
        version = template.start_new_version(self.manager)
        cable = make_product("CABLE", Category.CABLE)

        response = self.client.post(
            reverse("line-create", args=[version.id]),
            {"product": cable.id, "basis": "cable_route", "quantity": "50"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 201)
        self.assertIsNone(version.lines.get().quantity)

    def test_a_draft_line_can_be_removed(self):
        version = make_complete_on_grid(self.manager)
        line = version.lines.first()

        response = self.client.delete(reverse("line-detail", args=[line.id]))

        self.assertEqual(response.status_code, 204)


class ProductPickerTests(CatalogueTestCase):
    def test_the_picker_returns_every_match_unpaged(self):
        for number in range(30):
            make_product(f"P{number:02d}")

        response = self.client.get(reverse("product-list"), {"picker": "true"})

        self.assertEqual(len(response.json()), 30)


class QueryCountTests(CatalogueTestCase):
    def test_the_product_list_does_not_grow_with_its_rows(self):
        for number in range(3):
            make_product(f"A{number}")
        with CaptureQueriesContext(connection) as small:
            self.client.get(reverse("product-list"))

        for number in range(15):
            make_product(f"B{number}")
        with CaptureQueriesContext(connection) as large:
            self.client.get(reverse("product-list"))

        self.assertEqual(len(small), len(large))


class SimultaneousReviewTests(TransactionTestCase):
    def test_a_version_reviewed_twice_at_once_goes_live_once(self):
        make_user("mgr", Role.OPERATIONS_MANAGER)
        admin = make_user("admin", Role.ADMINISTRATOR)
        SizingDefaults.objects.get_or_create(
            cable_waste_factor="1.15", cable_termination_buffer_m="5"
        )
        version = make_complete_on_grid(admin)

        barrier = threading.Barrier(2)
        codes = []

        def review():
            client = Client(raise_request_exception=False)
            client.login(username="admin", password=PASSWORD)
            barrier.wait()
            codes.append(
                client.post(reverse("version-activate", args=[version.id])).status_code
            )
            connections.close_all()

        threads = [threading.Thread(target=review) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(codes), [200, 400])
