"""
F11 - installation evidence and customer acceptance.

What the crew records on the roof, and what the customer signs:

    InstallationReport  - the completed work, with its measurements.
    InstalledUnit       - which serials ended up on this roof.
    InstallationPhoto   - captioned evidence of the finished work.
    Acceptance          - the customer's decision on one exact revision.

Refusal is a valid outcome, not an error. A customer who will not sign
leaves the work open with a recorded reason, and the crew goes back.
Treating that as a failure would push people to record a signature that
was never given.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from apps.customers.models import SystemType


# The checks every installation has to answer before it can be submitted.
# Short on purpose: a list nobody can finish gets ticked without looking.
MANDATORY_CHECKS = [
    "mounting_secure",
    "earthing_connected",
    "dc_polarity_verified",
    "ac_isolator_labelled",
    "inverter_commissioned",
]


class ReportStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Awaiting customer acceptance"
    ACCEPTED = "accepted", "Accepted"
    REFUSED = "refused", "Refused by customer"


class Decision(models.TextChoices):
    ACCEPTED = "accepted", "Accepted"
    REFUSED = "refused", "Refused"


# ============================================================
# Report
# ============================================================

class InstallationReport(models.Model):
    """
    What was actually installed, as against what was sold.

    The capacity here is measured on site and can differ from the
    quotation. That difference is the point: the handover document has
    to say what the customer got, not what was hoped for.
    """

    job = models.OneToOneField(
        "scheduling.Job", on_delete=models.PROTECT, related_name="installation_report"
    )
    status = models.CharField(
        max_length=20, choices=ReportStatus.choices, default=ReportStatus.DRAFT
    )

    # Actual times on site, against the slot the job was booked into.
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    system_type = models.CharField(max_length=20, choices=SystemType.choices, blank=True)
    installed_capacity_kw = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.01"))],
    )

    # [{"item": "earthing_connected", "passed": true, "note": ""}, ...]
    checklist = models.JSONField(default=list)

    generation_test_kw = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        help_text="Output measured at the inverter during the test.",
    )
    generation_test_passed = models.BooleanField(null=True, blank=True)
    generation_test_notes = models.TextField(blank=True)
    notes = models.TextField(blank=True)

    # Frozen at submission. The customer signs this exact document.
    content_hash = models.CharField(max_length=64, blank=True)
    submitted_at = models.DateTimeField(null=True, blank=True)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="installation_reports",
    )
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            # A job that finished before it started is a typing error, and
            # it would corrupt every duration report downstream.
            models.CheckConstraint(
                condition=(models.Q(finished_at__isnull=True)
                           | models.Q(started_at__isnull=True)
                           | models.Q(finished_at__gt=models.F("started_at"))),
                name="installation_finishes_after_it_starts",
            ),
        ]

    def __str__(self):
        return f"Installation report for job {self.job_id}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Installation evidence is never deleted.")

    @property
    def is_editable(self):
        """Accepted work is frozen; a refusal sends it back for correction."""
        return self.status in (ReportStatus.DRAFT, ReportStatus.REFUSED)

    def missing_evidence(self):
        """Everything still needed before the customer can be asked to sign."""
        missing = []

        if self.started_at is None or self.finished_at is None:
            missing.append("the actual start and finish times")
        if not self.system_type:
            missing.append("the confirmed system type")
        if self.installed_capacity_kw is None:
            missing.append("the installed capacity")
        if self.generation_test_passed is None:
            missing.append("the generation test result")
        if not self.installed_units.exists():
            missing.append("the installed equipment, by serial")
        if not self.photos.exists():
            missing.append("at least one photograph of the finished work")

        answered = {
            entry.get("item") for entry in self.checklist
            if isinstance(entry, dict) and entry.get("passed") is not None
        }
        unanswered = [check for check in MANDATORY_CHECKS if check not in answered]
        if unanswered:
            missing.append("checklist items: " + ", ".join(
                check.replace("_", " ") for check in unanswered))

        return missing


# ============================================================
# Evidence
# ============================================================

class InstalledUnit(models.Model):
    """
    One serialized unit, tied to the roof it is now on.

    This is the link F13 follows years later when somebody rings up with
    a serial and no paperwork.
    """

    report = models.ForeignKey(
        InstallationReport, on_delete=models.PROTECT, related_name="installed_units"
    )
    unit = models.ForeignKey(
        "inventory.SerializedUnit", on_delete=models.PROTECT, related_name="installations"
    )
    position_note = models.CharField(
        max_length=200, blank=True, help_text="Where on the array or wall it sits."
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["report", "unit"], name="one_entry_per_unit_per_report"
            ),
        ]

    def __str__(self):
        return f"{self.unit.asset_id} on report {self.report_id}"


class InstallationPhoto(models.Model):
    """Captioned evidence. An uncaptioned photo is of nothing in particular."""

    report = models.ForeignKey(
        InstallationReport, on_delete=models.PROTECT, related_name="photos"
    )
    image = models.ImageField(upload_to="installation_photos/")
    caption = models.CharField(max_length=200)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.caption


# ============================================================
# Acceptance
# ============================================================

class InstallationAcceptance(models.Model):
    """
    The customer's decision on one exact revision of the report.

    Separate from quotation acceptance (F06) and from service resolution
    (F13). None of the three implies either of the others.
    """

    report = models.OneToOneField(
        InstallationReport, on_delete=models.PROTECT, related_name="acceptance"
    )
    decision = models.CharField(max_length=20, choices=Decision.choices)
    customer_name = models.CharField(max_length=150)
    signature = models.ImageField(upload_to="installation_signatures/", blank=True)
    refusal_reason = models.TextField(blank=True)

    # What was on the screen when they decided.
    document_revision = models.PositiveIntegerField()
    document_content_hash = models.CharField(max_length=64)

    witnessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="installation_acceptances",
    )
    decided_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            # Accepting needs a signature; refusing needs a reason. Each
            # outcome carries its own evidence, and neither is optional.
            models.CheckConstraint(
                condition=(models.Q(decision="accepted") & ~models.Q(signature=""))
                          | (models.Q(decision="refused") & ~models.Q(refusal_reason="")),
                name="each_decision_carries_its_evidence",
            ),
        ]

    def __str__(self):
        return f"{self.get_decision_display()} by {self.customer_name}"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("An acceptance record cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Acceptance evidence cannot be deleted.")
