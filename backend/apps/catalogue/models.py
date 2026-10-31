"""
F04 — catalogue, packages and component rules.

The catalogue holds what the company sells and the reviewed package
templates that turn an approved survey into a parts list.

    Product          — one thing that can go to site, or a labour line.
    ProductPrice     — a price from a date. Append-only, never edited.
    PackageTemplate  — what is offered, such as On-Grid 3 kW.
    PackageVersion   — one reviewed bill of materials for that offer.
    PackageLine      — one product on a version, and how much of it.

The rule that shapes this file: a version that has been reviewed never
changes. A quotation records the version it was built from, so editing
one would rewrite what a customer was told. Changes are a new version.

All catalogue amounts are INR and exclude tax. The column names say so,
per spec.md section 6. Tax is added from the product's GST rate.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from apps.core.api import business_date
from apps.core.models import record_event

SMALLEST_QUANTITY = Decimal("0.01")


# ============================================================
# Choices
# ============================================================

class Category(models.TextChoices):
    PANEL = "panel", "Solar panel"
    INVERTER = "inverter", "Inverter"
    BATTERY = "battery", "Battery"
    CHARGE_CONTROLLER = "charge_controller", "Charge controller"
    MOUNTING = "mounting", "Mounting structure"
    CABLE = "cable", "Cable"
    CONNECTOR = "connector", "Connector"
    PROTECTION = "protection", "Switch or protection device"
    EARTHING = "earthing", "Earthing material"
    SERVICE = "service", "Labour or service"
    OTHER = "other", "Other"


class TrackingMethod(models.TextChoices):
    """How an item is identified. See spec.md F08."""

    SERIALIZED = "serialized", "Serialized"
    BULK = "bulk", "Bulk, by batch"
    SERVICE = "service", "Service, no stock"


class PackageKind(models.TextChoices):
    PANEL_SET = "panel_set", "Solar Panel Set"
    ON_GRID = "on_grid", "On-Grid"
    OFF_GRID = "off_grid", "Off-Grid"
    INSTALLATION = "installation", "Installation service"


class QuantityBasis(models.TextChoices):
    """Where a line's quantity comes from."""

    FIXED = "fixed", "Fixed quantity"
    CABLE_ROUTE = "cable_route", "From the surveyed cable route"
    BATTERY_LOAD = "battery_load", "From the off-grid load and backup"


class VersionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ACTIVE = "active", "Active"
    RETIRED = "retired", "Retired"


# A package covers everything that goes to site, not just the headline
# items. See spec.md F04. A version missing one of these cannot go live.
ON_GRID_CATEGORIES = [
    Category.PANEL, Category.INVERTER, Category.MOUNTING, Category.CABLE,
    Category.CONNECTOR, Category.PROTECTION, Category.EARTHING, Category.SERVICE,
]
REQUIRED_CATEGORIES = {
    PackageKind.PANEL_SET: [Category.PANEL],
    PackageKind.ON_GRID: ON_GRID_CATEGORIES,
    PackageKind.OFF_GRID: [
        *ON_GRID_CATEGORIES, Category.BATTERY, Category.CHARGE_CONTROLLER,
    ],
    PackageKind.INSTALLATION: [Category.SERVICE],
}

# Kinds sold at a stated size.
SIZED_KINDS = [PackageKind.ON_GRID, PackageKind.OFF_GRID]


# ============================================================
# Warranty policy and sizing defaults
# ============================================================

# What a customer is promised. Changing any of these makes a new version
# of the policy (D015); renaming it does not.
WARRANTY_TERM_FIELDS = ("duration_months", "conditions", "fresh_period_on_replacement")


class WarrantyPolicy(models.Model):
    """
    Coverage a product is sold with.

    Configuration, not universal manufacturer terms. F12 snapshots the
    policy at delivery, so changing one never rewrites active coverage.
    """

    name = models.CharField(max_length=100, unique=True)
    version = models.PositiveIntegerField(default=1, editable=False)
    duration_months = models.PositiveIntegerField(validators=[MinValueValidator(1)])
    conditions = models.TextField(blank=True)

    # Off means a replacement inherits what was left on the original
    # (D020), which is what stops a swap extending cover for ever.
    fresh_period_on_replacement = models.BooleanField(
        default=False,
        help_text="A replacement gets a full new term instead of the remaining cover.",
    )

    class Meta:
        ordering = ["name"]
        verbose_name_plural = "warranty policies"
        constraints = [
            # A zero-month warranty is no warranty, and would only surface
            # when a delivery failed on it.
            models.CheckConstraint(
                condition=models.Q(duration_months__gt=0),
                name="warranty_policy_has_a_term",
            ),
        ]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        self._set_version()
        super().save(*args, **kwargs)

    def _set_version(self):
        """Judges by the stored row, so a stale copy cannot skip a version."""
        stored = (WarrantyPolicy.objects.filter(pk=self.pk)
                  .values("version", *WARRANTY_TERM_FIELDS).first())
        if stored is None:
            return

        changed = any(stored[name] != getattr(self, name) for name in WARRANTY_TERM_FIELDS)
        self.version = stored["version"] + 1 if changed else stored["version"]


class SizingDefaults(models.Model):
    """
    What a brand new template version starts with.

    One row, editable in the admin, because spec.md section 14 says
    these are settings and never constants in code. Later versions copy
    their figures from the version before.
    """

    cable_waste_factor = models.DecimalField(max_digits=4, decimal_places=2)
    cable_termination_buffer_m = models.DecimalField(max_digits=6, decimal_places=2)

    class Meta:
        verbose_name_plural = "sizing defaults"

    def __str__(self):
        return f"Waste {self.cable_waste_factor}, buffer {self.cable_termination_buffer_m} m"


# ============================================================
# Product
# ============================================================

class Product(models.Model):
    """One thing the company supplies, or a labour line."""

    sku = models.CharField(max_length=40, unique=True)
    revision = models.PositiveIntegerField(default=1)
    name = models.CharField(max_length=150)
    description = models.TextField(blank=True)
    category = models.CharField(max_length=20, choices=Category.choices)
    tracking_method = models.CharField(max_length=20, choices=TrackingMethod.choices)

    # Unit it is counted in, and the smallest amount it is stocked in.
    # Cable sold in 5 m lengths has unit "m" and a stocking quantity of 5,
    # and a calculated quantity rounds up to the next multiple.
    unit = models.CharField(max_length=20)
    stocking_quantity = models.DecimalField(
        max_digits=8, decimal_places=2, default=1,
        validators=[MinValueValidator(SMALLEST_QUANTITY)],
    )

    gst_rate_percent = models.DecimalField(max_digits=5, decimal_places=2)
    warranty_policy = models.ForeignKey(
        WarrantyPolicy, on_delete=models.PROTECT, null=True, blank=True,
        related_name="products",
    )

    # The technical attributes sizing depends on.
    rated_power_w = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    storage_kwh = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    nominal_voltage_v = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    is_repair_part = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["sku", "id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(gst_rate_percent__gte=0, gst_rate_percent__lte=100,
                                                      stocking_quantity__gt=0), name="product_valid_tax_and_stocking_unit"),
        ]

    def __str__(self):
        return f"{self.sku} {self.name}"

    def current_price(self):
        """
        The price in force today, or None.

        Reads self.prices.all() so a prefetched list is used and a
        catalogue page does not run one query per product.
        """
        today = business_date()
        in_force = [
            price for price in self.prices.all() if price.effective_from <= today
        ]
        return max(in_force, key=lambda price: price.effective_from, default=None)


class ProductPrice(models.Model):
    """
    A selling price and purchase cost from a date.

    Append-only. A price change is a new row, so what applied on any
    past date can always be read back.
    """

    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="prices")
    selling_price_excl_tax = models.DecimalField(max_digits=12, decimal_places=2)
    purchase_cost_excl_tax = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True
    )
    effective_from = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="prices_set"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(selling_price_excl_tax__gte=0) &
                                   (models.Q(purchase_cost_excl_tax__isnull=True) | models.Q(purchase_cost_excl_tax__gte=0)),
                                   name="product_price_nonnegative_amounts"),
            models.UniqueConstraint(
                fields=["product", "effective_from"],
                name="one_price_per_product_per_date",
            ),
        ]

    def __str__(self):
        return f"{self.product.sku} from {self.effective_from}"

    def save(self, *args, **kwargs):
        if self.pk and ProductPrice.objects.filter(pk=self.pk).exists():
            raise ValidationError("Prices are append-only. Add a price with a new effective date.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Price history cannot be deleted.")


# ============================================================
# Package template
# ============================================================

class PackageTemplate(models.Model):
    """What is offered: a kind and, for system packages, a size."""

    kind = models.CharField(max_length=20, choices=PackageKind.choices)
    capacity_kw = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    name = models.CharField(max_length=150)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["kind", "capacity_kw", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["kind", "capacity_kw"],
                name="one_template_per_kind_and_size",
            ),
            # NULL never matches in a unique constraint, so the sizeless
            # kinds need their own rule.
            models.UniqueConstraint(
                fields=["kind"],
                condition=models.Q(capacity_kw__isnull=True),
                name="one_sizeless_template_per_kind",
            ),
        ]

    def __str__(self):
        return self.name

    @property
    def active_version(self):
        """The version quotations may use. Reads a prefetched list if there is one."""
        for version in self.versions.all():
            if version.status == VersionStatus.ACTIVE:
                return version
        return None

    def clean(self):
        if self.kind in SIZED_KINDS and self.capacity_kw is None:
            raise ValidationError("This kind of package needs a capacity.")

    def start_new_version(self, created_by):
        """
        Opens a draft, copying the newest version's lines and figures.

        Locks the template so two people starting a version at the same
        time cannot be given the same number.
        """
        with transaction.atomic():
            PackageTemplate.objects.select_for_update().get(pk=self.pk)

            if self.versions.filter(status=VersionStatus.DRAFT).exists():
                raise ValidationError("This package already has a draft version.")

            latest = self.versions.order_by("-version_number").first()
            version = PackageVersion(
                template=self,
                version_number=latest.version_number + 1 if latest else 1,
                created_by=created_by,
                **_starting_figures(latest),
            )
            version.save()
            record_event(version, "draft_created", created_by,
                         after={"version_number": version.version_number})

            if latest:
                PackageLine.objects.bulk_create([
                    PackageLine(
                        version=version, product=line.product, basis=line.basis,
                        quantity=line.quantity, notes=line.notes,
                    )
                    for line in latest.lines.all()
                ])

        return version


def _starting_figures(latest):
    """Figures for a new version: the previous version's, else the defaults."""
    if latest:
        return {
            "cable_waste_factor": latest.cable_waste_factor,
            "cable_termination_buffer_m": latest.cable_termination_buffer_m,
            "battery_depth_of_discharge": latest.battery_depth_of_discharge,
        }

    defaults = SizingDefaults.objects.first()
    if defaults is None:
        raise ValidationError("Sizing defaults have not been set up.")

    return {
        "cable_waste_factor": defaults.cable_waste_factor,
        "cable_termination_buffer_m": defaults.cable_termination_buffer_m,
    }


# ============================================================
# Package version
# ============================================================

class PackageVersion(models.Model):
    """
    One bill of materials for a template.

    Editable only as a draft. Reviewing it makes it the active version
    and retires the one before. An unreviewed version can never produce
    a customer quotation (D028).
    """

    template = models.ForeignKey(
        PackageTemplate, on_delete=models.PROTECT, related_name="versions"
    )
    version_number = models.PositiveIntegerField()
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20, choices=VersionStatus.choices, default=VersionStatus.DRAFT
    )

    # Versioned with the package, so a reissued quotation reproduces the
    # quantity its version produced (D027).
    cable_waste_factor = models.DecimalField(
        max_digits=4, decimal_places=2, validators=[MinValueValidator(1)]
    )
    cable_termination_buffer_m = models.DecimalField(
        max_digits=6, decimal_places=2, validators=[MinValueValidator(0)]
    )

    # Share of a battery's stored energy that may be used. Needed only
    # where a line is sized from the off-grid load.
    battery_depth_of_discharge = models.DecimalField(
        max_digits=3, decimal_places=2, null=True, blank=True
    )

    notes = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="package_versions_created",
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True,
        related_name="package_versions_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-version_number"]
        constraints = [
            models.CheckConstraint(condition=models.Q(cable_waste_factor__gte=1, cable_termination_buffer_m__gte=0) &
                                   (models.Q(battery_depth_of_discharge__isnull=True) |
                                    models.Q(battery_depth_of_discharge__gt=0, battery_depth_of_discharge__lte=1)),
                                   name="package_valid_sizing_parameters"),
            models.UniqueConstraint(
                fields=["template", "version_number"],
                name="unique_version_number_per_template",
            ),
            # Quotation generation must never have two to choose from.
            models.UniqueConstraint(
                fields=["template"],
                condition=models.Q(status="active"),
                name="one_active_version_per_template",
            ),
            models.UniqueConstraint(
                fields=["template"],
                condition=models.Q(status="draft"),
                name="one_draft_version_per_template",
            ),
        ]

    def __str__(self):
        return f"{self.template.name} v{self.version_number}"

    @property
    def is_editable(self):
        return self.status == VersionStatus.DRAFT

    def save(self, *args, **kwargs):
        if self.pk:
            self._refuse_edit_unless_draft(kwargs.get("update_fields"))
        super().save(*args, **kwargs)

    def _refuse_edit_unless_draft(self, update_fields):
        """Judges by the stored status, so a stale copy cannot reopen a version."""
        stored_status = (
            PackageVersion.objects.filter(pk=self.pk)
            .values_list("status", flat=True)
            .first()
        )
        is_status_write = update_fields and set(update_fields) <= {
            "status", "reviewed_by", "reviewed_at",
        }
        if stored_status != VersionStatus.DRAFT and not is_status_write:
            raise ValidationError(
                f"Version {self.version_number} has been reviewed and cannot "
                "be edited. Start a new version instead."
            )

    # --- review ------------------------------------------------------

    def problems(self):
        """Everything stopping this version going live, in plain words."""
        lines = list(self.lines.select_related("product").prefetch_related("product__prices"))
        if not lines:
            return ["This version has no lines."]

        found = []
        categories = {line.product.category for line in lines}
        for category in REQUIRED_CATEGORIES[self.template.kind]:
            if category not in categories:
                found.append(f"Missing a line for: {Category(category).label}.")

        for line in lines:
            found.extend(line.problems(self))

        return found

    def activate(self, reviewer):
        """
        Makes this the version quotations use.

        Runs with the template locked, so two reviews at once cannot
        both retire the same version and leave two active.
        """
        if not reviewer.has_role("administrator"):
            raise ValidationError("Only an administrator may review and activate a package.")
        with transaction.atomic():
            PackageTemplate.objects.select_for_update().get(pk=self.template_id)
            self.refresh_from_db(fields=["status"])

            if self.status != VersionStatus.DRAFT:
                raise ValidationError("Only a draft version can be reviewed.")

            problems = self.problems()
            if problems:
                raise ValidationError(problems)

            current = self.template.versions.filter(status=VersionStatus.ACTIVE).first()
            if current:
                current.status = VersionStatus.RETIRED
                current.save(update_fields=["status"])

            self.status = VersionStatus.ACTIVE
            self.reviewed_by = reviewer
            self.reviewed_at = timezone.now()
            self.save(update_fields=["status", "reviewed_by", "reviewed_at"])
            record_event(self, "activated", reviewer,
                         before={"status": VersionStatus.DRAFT},
                         after={"status": VersionStatus.ACTIVE})
            if current:
                record_event(current, "retired", reviewer,
                             before={"status": VersionStatus.ACTIVE},
                             after={"status": VersionStatus.RETIRED})


# ============================================================
# Package line
# ============================================================

class PackageLine(models.Model):
    """One product on a version, and where its quantity comes from."""

    version = models.ForeignKey(PackageVersion, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey(Product, on_delete=models.PROTECT, related_name="package_lines")
    basis = models.CharField(
        max_length=20, choices=QuantityBasis.choices, default=QuantityBasis.FIXED
    )

    # Set only for a fixed line. The other bases are calculated from the
    # survey, so a quantity typed here would only be misleading.
    quantity = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    notes = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(condition=models.Q(basis="fixed", quantity__isnull=False, quantity__gt=0) |
                                   (models.Q(basis__in=["cable_route", "battery_load"]) & models.Q(quantity__isnull=True)),
                                   name="package_line_valid_quantity_basis"),
            models.UniqueConstraint(
                fields=["version", "product"], name="one_line_per_product_per_version",
            ),
        ]

    def __str__(self):
        return f"{self.version}: {self.product.sku}"

    def save(self, *args, **kwargs):
        self._require_draft()
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._require_draft()
        return super().delete(*args, **kwargs)

    def _require_draft(self):
        stored_status = (
            PackageVersion.objects.filter(pk=self.version_id)
            .values_list("status", flat=True)
            .first()
        )
        if stored_status != VersionStatus.DRAFT:
            raise ValidationError("A reviewed version cannot be changed.")

    def problems(self, version):
        """Why this line cannot go live, in plain words."""
        product = self.product
        found = []

        if not product.is_active:
            found.append(f"{product.sku} is no longer active.")

        if product.current_price() is None:
            found.append(f"{product.sku} has no selling price.")

        if self.basis == QuantityBasis.FIXED and not self.quantity:
            found.append(f"{product.sku} needs a quantity.")

        if self.basis == QuantityBasis.CABLE_ROUTE and product.category != Category.CABLE:
            found.append(f"{product.sku} is not cable, so it cannot follow the cable route.")

        if self.basis == QuantityBasis.BATTERY_LOAD:
            if not product.storage_kwh:
                found.append(f"{product.sku} needs its storage capacity in kWh.")
            if not version.battery_depth_of_discharge:
                found.append("A battery sized from the load needs a depth of discharge.")

        return found
