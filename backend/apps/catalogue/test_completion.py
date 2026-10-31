"""F04 dummy coverage and validation: repeat-safe seeding, review gates and invalid prices/quantities."""

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from .models import PackageTemplate, PackageVersion, Product, VersionStatus
from .tests import make_complete_on_grid


class CatalogueCompletionTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser("seed_owner", "owner@example.invalid", "test-only")
        self.client.force_login(self.admin)

    def test_dummy_seed_covers_all_required_packages_and_is_repeat_safe(self):
        call_command("seed_catalogue", verbosity=0)
        self.assertEqual(PackageTemplate.objects.count(), 12)
        self.assertEqual(PackageVersion.objects.filter(status=VersionStatus.ACTIVE).count(), 0)
        self.assertTrue(all("DUMMY" in name for name in PackageTemplate.objects.values_list("name", flat=True)))
        product_count = Product.objects.count()
        call_command("seed_catalogue", verbosity=0)
        self.assertEqual(Product.objects.count(), product_count)
        self.assertEqual(PackageVersion.objects.count(), 12)
        for version in PackageVersion.objects.select_related("template"):
            self.assertEqual(version.problems(), [], version.template.name)

    def test_seed_leaves_existing_reviewed_packages_unchanged(self):
        version = make_complete_on_grid(self.admin)
        version.activate(self.admin)
        previous_name = version.template.name
        previous_lines = list(version.lines.values_list("product_id", "quantity"))
        call_command("seed_catalogue", verbosity=0)
        version.refresh_from_db()
        self.assertEqual(version.status, VersionStatus.ACTIVE)
        self.assertEqual(version.template.name, previous_name)
        self.assertEqual(list(version.lines.values_list("product_id", "quantity")), previous_lines)

    def test_invalid_gst_price_and_fixed_quantity_are_rejected_by_field(self):
        version = make_complete_on_grid(self.admin)
        product = version.lines.first().product
        response = self.client.patch(reverse("product-detail", args=[product.pk]), {"revision": product.revision, "gst_rate_percent": "-1"}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("gst_rate_percent", response.json())
        response = self.client.post(reverse("product-prices", args=[product.pk]), {
            "selling_price_excl_tax": "-1", "effective_from": "2099-01-01",
        }, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        response = self.client.patch(reverse("line-detail", args=[version.lines.first().pk]),
                                     {"revision": version.revision, "quantity": "0"}, content_type="application/json")
        self.assertEqual(response.status_code, 400)

    def test_stale_product_and_package_edits_cannot_overwrite_new_values(self):
        version = make_complete_on_grid(self.admin)
        product = version.lines.first().product
        product_url = reverse("product-detail", args=[product.pk])
        data = {"revision": product.revision, "name": "Reviewed product name"}
        self.assertEqual(self.client.patch(product_url, data, content_type="application/json").status_code, 200)
        self.assertEqual(self.client.patch(product_url, data, content_type="application/json").status_code, 409)
        version_url = reverse("version-detail", args=[version.pk])
        values = {"revision": version.revision, "cable_waste_factor": "1.25"}
        self.assertEqual(self.client.patch(version_url, values, content_type="application/json").status_code, 200)
        self.assertEqual(self.client.patch(version_url, values, content_type="application/json").status_code, 409)
