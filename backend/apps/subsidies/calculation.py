"""Compute exact eligible estimates separately from quotation totals, using Decimal INR."""

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Q
from rest_framework.exceptions import ValidationError

from apps.core.api import business_date
from .models import SchemeVersion

PAISE = Decimal("0.01")


def estimate_subsidies(site, survey_revision, facts):
    """Newest effective version per scheme; unknown conditions block a partial estimate."""
    today = business_date()
    rules = SchemeVersion.objects.filter(
        is_active=True, effective_from__lte=today,
        customer_type=site.customer.customer_type,
        system_type=survey_revision.recommended_system_type,
    ).filter(Q(jurisdiction="") | Q(jurisdiction=site.state)).filter(
        Q(effective_until__isnull=True) | Q(effective_until__gt=today)
    ).order_by("scheme", "-effective_from", "-version", "-id")
    seen = set()
    estimates = []
    for rule in rules:
        if rule.scheme in seen:
            continue
        seen.add(rule.scheme)
        missing = [condition for condition in rule.conditions if condition not in facts]
        if missing:
            raise ValidationError({"subsidy_facts": ["Confirm eligibility: " + ", ".join(missing)]})
        if any(facts[condition] is not True for condition in rule.conditions):
            continue
        amount = calculate_amount(rule.calculation, survey_revision.recommended_capacity_kw)
        estimates.append({
            "rule_id": rule.pk, "scheme": rule.scheme, "version": rule.version,
            "authority": rule.authority, "jurisdiction": rule.jurisdiction or "Central",
            "rule_type": rule.rule_type, "amount": str(amount),
            "unit": "INR/kWh" if rule.rule_type == "generation" else "INR",
            "source_url": rule.source_url, "last_checked": str(rule.last_checked),
            "provenance": rule.provenance,
            "assumptions": {"customer_type": site.customer.customer_type,
                            "system_type": survey_revision.recommended_system_type,
                            "capacity_kw": str(survey_revision.recommended_capacity_kw),
                            **{key: facts[key] for key in rule.conditions}},
            "required_documents": rule.required_documents,
        })
    return estimates


def calculate_amount(formula, capacity_kw):
    method = formula["method"]
    if method in ("fixed", "per_kwh"):
        amount = Decimal(formula["amount"])
    elif method == "per_kw":
        amount = capacity_kw * Decimal(formula["rate"])
    elif method == "slabs":
        amount = Decimal("0")
        previous_limit = Decimal("0")
        for slab in formula["slabs"]:
            upper_limit = Decimal(slab["up_to_kw"])
            covered_kw = max(Decimal("0"), min(capacity_kw, upper_limit) - previous_limit)
            amount += covered_kw * Decimal(slab["rate"])
            previous_limit = upper_limit
    else:
        raise ValidationError({"subsidy": ["The configured rule has no exact calculation."]})
    if formula.get("cap") is not None:
        amount = min(amount, Decimal(formula["cap"]))
    return amount.quantize(PAISE, rounding=ROUND_HALF_UP)
