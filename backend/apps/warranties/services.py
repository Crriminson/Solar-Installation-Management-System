"""
Issuing and replacing warranties (F12).

issue_warranties runs inside delivery's transaction, so a delivery and
its warranties commit together or not at all. Nothing here takes a date
from a person: start and expiry come from the delivery and the policy.

record_replacement is the warranty half of a replacement. The physical
half, issuing the new unit and returning the old one, belongs to the F13
ticket, which calls this once the new unit is with the customer (D051).
"""

import logging

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.api import business_date
from apps.core.models import record_event
from apps.inventory.models import SerializedUnit, StockStatus

from .coverage import coverage_expiry
from .models import AssetWarranty, CoverageBasis

LOGGER = logging.getLogger(__name__)

# Where a replacement unit has to be before cover can move onto it.
ISSUED_STATUSES = [StockStatus.DELIVERED, StockStatus.INSTALLED]

# The terms a replacement carries over from the warranty it replaces.
SNAPSHOT_FIELDS = ("policy", "policy_name", "policy_version", "duration_months",
                   "conditions", "fresh_period_on_replacement")


# ============================================================
# Issuing
# ============================================================

def issue_warranties(fulfilment, actor):
    """
    Starts cover on every eligible unit this delivery handed over.

    Eligible means serialized with a warranty policy. Cable has no unit
    identity, so bulk stock gets nothing. A serialized unit with no
    policy does not stop the delivery, because the goods really did
    arrive, but it is reported rather than quietly left uncovered.

    The start date is the Kolkata date of delivered_at. Not today, since
    delivery may be keyed in late, and not the UTC date, which is the day
    before for anything delivered in the first hours of the morning.
    """
    units = (SerializedUnit.objects
             .filter(order_id=fulfilment.order_id, status=StockStatus.DELIVERED)
             .select_related("product__warranty_policy")
             .order_by("id"))
    start = business_date(fulfilment.delivered_at)

    issued, not_covered = [], []
    for unit in units:
        policy = unit.product.warranty_policy
        if policy is None:
            not_covered.append(unit.asset_id)
            continue

        warranty = AssetWarranty.objects.create(
            unit=unit, customer_id=unit.customer_id, site_id=unit.site_id,
            order_id=fulfilment.order_id, fulfilment=fulfilment,
            delivered_at=fulfilment.delivered_at, created_by=actor,
            policy=policy, policy_name=policy.name, policy_version=policy.version,
            duration_months=policy.duration_months, conditions=policy.conditions,
            fresh_period_on_replacement=policy.fresh_period_on_replacement,
            coverage_basis=CoverageBasis.DELIVERY, coverage_start=start,
            coverage_expires_on=coverage_expiry(start, policy.duration_months),
        )
        record_event(warranty, "issued", actor, after=_coverage(warranty))
        issued.append(warranty)

    if not_covered:
        LOGGER.warning("Delivered without warranty cover: fulfilment=%s units=%s",
                       fulfilment.pk, ", ".join(not_covered))
    record_event(fulfilment, "warranties_issued", actor,
                 after={"issued": len(issued), "not_covered": not_covered})
    return issued


# ============================================================
# Replacement
# ============================================================

@transaction.atomic
def record_replacement(warranty_id, replacement_unit_id, data, actor):
    """
    Moves cover from a failed unit onto the one that replaced it.

    Expects complaint_at, replaced_at and reason in data. The original
    row is left exactly as it was: the new row points back at it, so both
    serials stay linked and the failed unit's history is intact.

    Terms come from the original's snapshot, not the live policy, so a
    policy change since delivery cannot alter what the customer receives.
    """
    # Warranty first, then unit. Anything else locking both must keep to
    # this order or two replacements could deadlock.
    original = AssetWarranty.objects.select_for_update().filter(pk=warranty_id).first()
    if original is None:
        raise NotFound()
    unit = SerializedUnit.objects.select_for_update().filter(pk=replacement_unit_id).first()
    if unit is None:
        raise NotFound()

    reason = data.get("reason", "").strip()
    _check_replacement(original, unit, data, reason)

    replaced_on = business_date(data["replaced_at"])
    basis, start, expires = _replacement_cover(original, replaced_on)

    replacement = AssetWarranty.objects.create(
        unit=unit, customer_id=original.customer_id, site_id=original.site_id,
        order_id=original.order_id, delivered_at=data["replaced_at"], created_by=actor,
        coverage_basis=basis, coverage_start=start, coverage_expires_on=expires,
        replaces=original, replacement_reason=reason,
        **{name: getattr(original, name) for name in SNAPSHOT_FIELDS},
    )
    record_event(replacement, "issued", actor, after=_coverage(replacement), reason=reason)
    record_event(original, "replaced", actor, after={"replaced_by": replacement.pk},
                 reason=reason)
    return replacement


def _check_replacement(original, unit, data, reason):
    if not reason:
        raise ValidationError({"reason": ["Say why this unit was replaced."]})
    if original.is_replaced:
        raise ValidationError({"warranty": ["This unit has already been replaced."]})
    if unit.pk == original.unit_id:
        raise ValidationError({"unit": ["A unit cannot replace itself."]})

    if unit.status not in ISSUED_STATUSES or unit.customer_id != original.customer_id:
        raise ValidationError(
            {"unit": [f"{unit.asset_id} has not been delivered to this customer."]}
        )
    if AssetWarranty.objects.in_cover(business_date()).filter(unit=unit).exists():
        raise ValidationError({"unit": [f"{unit.asset_id} is already in cover."]})

    complaint_at, replaced_at = data["complaint_at"], data["replaced_at"]
    if replaced_at > timezone.now():
        raise ValidationError({"replaced_at": ["A replacement cannot be in the future."]})
    if business_date(replaced_at) < original.coverage_start:
        raise ValidationError(
            {"replaced_at": ["That is before this warranty started."]}
        )
    if complaint_at > replaced_at:
        raise ValidationError(
            {"complaint_at": ["The complaint cannot come after the replacement."]}
        )
    if not original.covers(business_date(complaint_at)):
        raise ValidationError(
            {"complaint_at": ["The complaint falls outside cover. Send it to review."]}
        )


def _replacement_cover(original, replaced_on):
    """Basis, start and expiry of the cover a replacement receives."""
    if original.fresh_period_on_replacement:
        expires = coverage_expiry(replaced_on, original.duration_months)
        return CoverageBasis.FRESH, replaced_on, expires

    # The expiry never moves, which is what stops repeated swaps extending
    # cover (D020). A swap made after expiry has nothing left to inherit,
    # so the window closes to nothing rather than running backwards (D050).
    expires = original.coverage_expires_on
    return CoverageBasis.INHERITED, min(replaced_on, expires), expires


# ============================================================
# Reading
# ============================================================

def replacement_history(warranty):
    """
    Every warranty in this unit's line, oldest first.

    One query per link. Only the record view walks this, and a chain is
    as long as the number of times one roof has lost the same inverter.
    """
    earliest = warranty
    while earliest.replaces_id:
        earliest = earliest.replaces

    history = [earliest]
    while history[-1].is_replaced:
        history.append(history[-1].replaced_by)
    return history


def _coverage(warranty):
    return {
        "basis": warranty.coverage_basis,
        "start": str(warranty.coverage_start),
        "expires": str(warranty.coverage_expires_on),
        "policy": warranty.policy_name,
        "policy_version": warranty.policy_version,
    }
