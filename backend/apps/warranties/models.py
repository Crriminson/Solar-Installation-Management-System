"""
F12 - warranties.

One record, spec.md section 8's AssetWarranty: what covers one physical
unit, for whom, and until when.

A warranty is written once and never edited. It holds its own copy of
the policy, so a later catalogue change cannot rewrite what a customer
was promised, and a replacement is a new row pointing at the old one, so
the failed unit's history survives.

Dates are Asia/Kolkata calendar dates. Coverage is start-inclusive and
expiry-exclusive: coverage_expires_on is the first day not covered.
"""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from apps.core.api import business_date


# ============================================================
# Choices
# ============================================================

class CoverageBasis(models.TextChoices):
    """Why a warranty's dates are what they are."""

    DELIVERY = "delivery", "From delivery"
    INHERITED = "inherited", "Inherited from the replaced unit"
    FRESH = "fresh", "Fresh period on replacement"


class WarrantyStatus(models.TextChoices):
    """
    Worked out on read, never stored.

    A stored status would need a daily job to expire it, and one missed
    run would show a dead warranty as live.
    """

    IN_COVER = "in_cover", "In cover"
    EXPIRED = "expired", "Expired"
    REPLACED = "replaced", "Replaced"


# ============================================================
# Warranty
# ============================================================

class AssetWarrantyQuerySet(models.QuerySet):
    def in_cover(self, on_date):
        return self.filter(replaced_by__isnull=True, coverage_start__lte=on_date,
                           coverage_expires_on__gt=on_date)

    def expired(self, on_date):
        return self.filter(replaced_by__isnull=True, coverage_expires_on__lte=on_date)

    def replaced(self):
        return self.filter(replaced_by__isnull=False)


class AssetWarranty(models.Model):
    """
    Coverage on one unit, from one delivery or one replacement.

    There is no "one warranty per unit" rule. A returned unit can be sold
    again, and that sale has its own cover for a different customer.
    """

    unit = models.ForeignKey(
        "inventory.SerializedUnit", on_delete=models.PROTECT, related_name="warranties"
    )
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    site = models.ForeignKey("customers.Site", on_delete=models.PROTECT)
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT)

    # The delivery that started this cover. Empty on a replacement, which
    # reaches the customer through a ticket rather than a packing list.
    fulfilment = models.ForeignKey(
        "fulfilment.Fulfilment", on_delete=models.PROTECT,
        null=True, blank=True, related_name="warranties",
    )
    delivered_at = models.DateTimeField(
        help_text="When this unit actually reached the customer."
    )

    # --- the policy as it stood. These count, never the live policy. ---
    policy = models.ForeignKey("catalogue.WarrantyPolicy", on_delete=models.PROTECT)
    policy_name = models.CharField(max_length=100)
    policy_version = models.PositiveIntegerField()
    duration_months = models.PositiveIntegerField()
    conditions = models.TextField(blank=True)
    fresh_period_on_replacement = models.BooleanField()

    # --- coverage ---
    coverage_basis = models.CharField(max_length=20, choices=CoverageBasis.choices)
    coverage_start = models.DateField()
    coverage_expires_on = models.DateField(help_text="First date not covered.")

    # --- replacement history ---
    replaces = models.OneToOneField(
        "self", on_delete=models.PROTECT, null=True, blank=True,
        related_name="replaced_by",
    )
    replacement_reason = models.TextField(blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="warranties_issued",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AssetWarrantyQuerySet.as_manager()

    class Meta:
        ordering = ["-id"]
        verbose_name_plural = "asset warranties"
        constraints = [
            # A repeated delivery must not produce a second warranty.
            models.UniqueConstraint(
                fields=["unit", "fulfilment"], name="one_warranty_per_unit_per_delivery"
            ),
            # Equal is allowed: a replacement made after expiry has nothing
            # left to inherit, so its window is empty (D050).
            models.CheckConstraint(
                condition=models.Q(coverage_start__lte=models.F("coverage_expires_on")),
                name="warranty_window_runs_forwards",
            ),
            models.CheckConstraint(
                condition=models.Q(duration_months__gt=0),
                name="warranty_has_a_term",
            ),
            # Cover comes from a delivery or from a reasoned replacement.
            models.CheckConstraint(
                condition=(
                    models.Q(coverage_basis="delivery", fulfilment__isnull=False,
                             replaces__isnull=True, replacement_reason="")
                    | (models.Q(coverage_basis__in=["inherited", "fresh"],
                                fulfilment__isnull=True, replaces__isnull=False)
                       & ~models.Q(replacement_reason=""))
                ),
                name="warranty_states_its_origin",
            ),
        ]

    def __str__(self):
        return f"{self.policy_name} on unit {self.unit_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError(
                "A warranty is never edited. A replacement is a new record."
            )
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Warranty records are never deleted.")

    # --- coverage ---------------------------------------------------------

    @property
    def is_replaced(self):
        return hasattr(self, "replaced_by")

    @property
    def cover_ends_on(self):
        """
        The first date this warranty no longer covers.

        Usually its expiry, but from the day a unit is swapped the cover
        belongs to the replacement. The stored expiry stays as it was.
        """
        if self.is_replaced:
            return min(self.coverage_expires_on, self.replaced_by.coverage_start)
        return self.coverage_expires_on

    def covers(self, on_date):
        """
        Whether a problem raised on this date is in cover.

        Pass the date the complaint was recorded, never the date somebody
        got round to it: a technician backlog must not expire a valid
        claim (D021).
        """
        return self.coverage_start <= on_date < self.cover_ends_on

    @property
    def status(self):
        if self.is_replaced:
            return WarrantyStatus.REPLACED
        if self.covers(business_date()):
            return WarrantyStatus.IN_COVER
        return WarrantyStatus.EXPIRED

    @property
    def last_covered_on(self):
        """
        The final date in cover, because "expires 1 March" reads as if
        1 March were covered. None when no day was ever covered (D050).
        """
        if self.cover_ends_on <= self.coverage_start:
            return None
        return self.cover_ends_on - timedelta(days=1)
