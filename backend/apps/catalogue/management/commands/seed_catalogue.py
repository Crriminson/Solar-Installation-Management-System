"""
Loads example products and two draft packages for a demo.

The prices and parts are placeholders, not an engineering bill of
materials. Both packages stay as unreviewed drafts on purpose: the team
authors the real ones and the owner reviews them (D028).

    manage.py seed_catalogue
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.catalogue.models import (
    Category,
    PackageKind,
    PackageLine,
    PackageTemplate,
    Product,
    ProductPrice,
    QuantityBasis,
    TrackingMethod,
    WarrantyPolicy,
)

GST_PERCENT = "12.00"
GST_SERVICE_PERCENT = "18.00"
DEMO_DEPTH_OF_DISCHARGE = "0.80"

# sku, name, category, tracking, unit, selling price, cost, extra fields
PRODUCTS = [
    ("PNL-540", "540 W mono panel", Category.PANEL, TrackingMethod.SERIALIZED, "piece", "14500", "12000", {"rated_power_w": "540"}),
    ("INV-3K", "3 kW on-grid inverter", Category.INVERTER, TrackingMethod.SERIALIZED, "piece", "32000", "26500", {"rated_power_w": "3000"}),
    ("INV-3K-OFF", "3 kW off-grid inverter", Category.INVERTER, TrackingMethod.SERIALIZED, "piece", "38000", "31500", {"rated_power_w": "3000"}),
    ("BAT-2K4", "2.4 kWh battery", Category.BATTERY, TrackingMethod.SERIALIZED, "piece", "24000", "20000", {"storage_kwh": "2.40", "nominal_voltage_v": "24"}),
    ("CTR-40A", "40 A charge controller", Category.CHARGE_CONTROLLER, TrackingMethod.SERIALIZED, "piece", "6500", "5200", {}),
    ("MNT-RAIL", "Mounting rail set", Category.MOUNTING, TrackingMethod.BULK, "set", "4200", "3400", {}),
    ("CBL-DC4", "DC cable 4 mm²", Category.CABLE, TrackingMethod.BULK, "m", "65", "48", {"stocking_quantity": "5"}),
    ("CBL-AC4", "AC cable 4 mm²", Category.CABLE, TrackingMethod.BULK, "m", "55", "41", {"stocking_quantity": "5"}),
    ("CON-MC4", "MC4 connector pair", Category.CONNECTOR, TrackingMethod.BULK, "pair", "120", "85", {}),
    ("PRT-MCB", "AC and DC protection box", Category.PROTECTION, TrackingMethod.BULK, "piece", "5200", "4100", {}),
    ("ERT-KIT", "Earthing kit", Category.EARTHING, TrackingMethod.BULK, "set", "3200", "2500", {}),
]

SERVICES = [
    ("SVC-INSTALL", "Installation labour", "job", "12000"),
    ("SVC-HOUR", "Repair labour", "hour", "450"),
]

# sku, quantity (None for a calculated line), basis
ON_GRID_LINES = [
    ("PNL-540", "6", QuantityBasis.FIXED),
    ("INV-3K", "1", QuantityBasis.FIXED),
    ("MNT-RAIL", "1", QuantityBasis.FIXED),
    ("CBL-DC4", None, QuantityBasis.CABLE_ROUTE),
    ("CBL-AC4", None, QuantityBasis.CABLE_ROUTE),
    ("CON-MC4", "4", QuantityBasis.FIXED),
    ("PRT-MCB", "1", QuantityBasis.FIXED),
    ("ERT-KIT", "1", QuantityBasis.FIXED),
    ("SVC-INSTALL", "1", QuantityBasis.FIXED),
]
OFF_GRID_LINES = [
    ("INV-3K-OFF", "1", QuantityBasis.FIXED),
    ("BAT-2K4", None, QuantityBasis.BATTERY_LOAD),
    ("CTR-40A", "1", QuantityBasis.FIXED),
    *[line for line in ON_GRID_LINES if line[0] != "INV-3K"],
]


class Command(BaseCommand):
    help = "Loads example products and two draft packages for a demo."

    @transaction.atomic
    def handle(self, *args, **options):
        author = get_user_model().objects.filter(is_superuser=True).first()
        if author is None:
            raise CommandError("Run createsuperuser first.")

        if Product.objects.exists():
            raise CommandError("The catalogue already has products.")

        self._add_products(author)
        self._add_package(PackageKind.ON_GRID, "On-Grid 3 kW", ON_GRID_LINES, author)
        self._add_package(PackageKind.OFF_GRID, "Off-Grid 3 kW", OFF_GRID_LINES, author)

        self.stdout.write(self.style.SUCCESS("Example catalogue loaded."))

    def _add_products(self, author):
        panel_policy = WarrantyPolicy.objects.get(name="Panel")
        equipment_policy = WarrantyPolicy.objects.get(name="Inverter and battery")

        for sku, name, category, tracking, unit, price, cost, extra in PRODUCTS:
            policy = None
            if category == Category.PANEL:
                policy = panel_policy
            elif tracking == TrackingMethod.SERIALIZED:
                policy = equipment_policy

            product = Product.objects.create(
                sku=sku, name=name, category=category, tracking_method=tracking,
                unit=unit, gst_rate_percent=GST_PERCENT, warranty_policy=policy,
                **extra,
            )
            self._add_price(product, price, cost, author)

        for sku, name, unit, price in SERVICES:
            product = Product.objects.create(
                sku=sku, name=name, category=Category.SERVICE, unit=unit,
                tracking_method=TrackingMethod.SERVICE,
                gst_rate_percent=GST_SERVICE_PERCENT,
            )
            self._add_price(product, price, None, author)

    def _add_price(self, product, price, cost, author):
        ProductPrice.objects.create(
            product=product, selling_price_excl_tax=price,
            purchase_cost_excl_tax=cost, effective_from=timezone.localdate(),
            created_by=author,
        )

    def _add_package(self, kind, name, lines, author):
        template = PackageTemplate.objects.create(kind=kind, capacity_kw="3.00", name=name)
        version = template.start_new_version(author)

        if kind == PackageKind.OFF_GRID:
            version.battery_depth_of_discharge = DEMO_DEPTH_OF_DISCHARGE
            version.save()

        for sku, quantity, basis in lines:
            PackageLine.objects.create(
                version=version, product=Product.objects.get(sku=sku),
                basis=basis, quantity=quantity,
            )
