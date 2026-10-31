"""Data-driven capital and generation incentive rules with versioned provenance."""

from django.core.exceptions import ValidationError
from django.db import models
from decimal import Decimal, InvalidOperation


class SchemeVersion(models.Model):
    scheme = models.CharField(max_length=120)
    version = models.PositiveIntegerField()
    authority = models.CharField(max_length=150)
    jurisdiction = models.CharField(max_length=60, blank=True)  # blank means central
    customer_type = models.CharField(max_length=20, default="residential")
    system_type = models.CharField(max_length=20, default="on_grid")
    rule_type = models.CharField(max_length=20, choices=[("capital", "Capital"), ("generation", "Per-kWh incentive")])
    # Conditions are explicitly confirmed facts, such as beneficiary or SC/ST status.
    conditions = models.JSONField(default=list, blank=True)
    calculation = models.JSONField()
    required_documents = models.JSONField(default=list, blank=True)
    effective_from = models.DateField()
    effective_until = models.DateField(null=True, blank=True)
    source_url = models.URLField()
    last_checked = models.DateField()
    provenance = models.TextField()
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["scheme", "-version", "-id"]
        constraints = [models.UniqueConstraint(fields=["scheme", "version"], name="unique_subsidy_scheme_version")]

    def clean(self):
        if self.effective_until and self.effective_until <= self.effective_from:
            raise ValidationError("The end date must follow the start date (end-exclusive).")
        formula = self.calculation
        if not isinstance(formula, dict) or formula.get("method") not in ("fixed", "per_kw", "slabs", "per_kwh"):
            raise ValidationError("Use an exact fixed, per_kw, slabs or per_kwh calculation.")
        if not isinstance(self.conditions, list) or any(not isinstance(value, str) for value in self.conditions):
            raise ValidationError("Conditions must be a list of named eligibility facts.")
        if (self.rule_type == "generation") != (formula["method"] == "per_kwh"):
            raise ValidationError("Per-kWh incentives must use the generation rule type.")
        try:
            if formula["method"] in ("fixed", "per_kwh"):
                amounts = [Decimal(formula["amount"])]
            elif formula["method"] == "per_kw":
                amounts = [Decimal(formula["rate"])]
            else:
                previous = Decimal("0")
                amounts = []
                for slab in formula["slabs"]:
                    upper = Decimal(slab["up_to_kw"])
                    if not upper.is_finite() or upper <= previous:
                        raise ValueError()
                    previous = upper
                    amounts.append(Decimal(slab["rate"]))
                if not amounts:
                    raise ValueError()
            if formula.get("cap") is not None:
                amounts.append(Decimal(formula["cap"]))
            if any(not amount.is_finite() or amount < 0 for amount in amounts):
                raise ValueError()
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ValidationError("Enter exact non-negative decimal amounts and ascending capacity slabs.")

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk, is_active=True).exists():
            raise ValidationError("Active rule versions are immutable. Add a new dated version.")
        self.full_clean()
        super().save(*args, **kwargs)
