"""
F03 — site survey and approval.

A technician visits the roof and records the physical facts a quotation
depends on. Nothing may be quoted to a customer until an approver has
signed that survey off.

Two records, because a survey can be sent back and redone:

    Survey          — one per enquiry. The ongoing conversation.
    SurveyRevision  — one attempt at recording the site. Immutable
                      once submitted.
    SurveyPhoto     — evidence attached to a revision.

The revision is where the rule lives: an approved revision is frozen
for good, because a quotation is built from it and must stay
reproducible. Changing anything afterwards means a new revision and a
fresh approval.
"""

from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone

from apps.customers.models import Enquiry, SystemType
from apps.core.models import record_event


# ============================================================
# Choices
# ============================================================

class RevisionStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    SUBMITTED = "submitted", "Submitted"
    CHANGES_REQUESTED = "changes_requested", "Changes requested"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    SUPERSEDED = "superseded", "Superseded"


# Which statuses may follow which. A revision cannot be approved
# straight from draft: somebody has to submit it for review first.
ALLOWED_REVISION_CHANGES = {
    RevisionStatus.DRAFT: [RevisionStatus.SUBMITTED],
    RevisionStatus.SUBMITTED: [
        RevisionStatus.APPROVED,
        RevisionStatus.CHANGES_REQUESTED,
        RevisionStatus.REJECTED,
    ],
    # A requested correction is resubmitted on the same revision.
    # Its prior submission remains in the audit history.
    RevisionStatus.CHANGES_REQUESTED: [RevisionStatus.SUBMITTED],
    # An approval ends only when a newer revision is approved. Until then
    # it stays in force, so a quotation always has one source.
    RevisionStatus.APPROVED: [RevisionStatus.SUPERSEDED],
    RevisionStatus.REJECTED: [],
    RevisionStatus.SUPERSEDED: [],
}

# A revision nobody can edit any more.
LOCKED_STATUSES = [
    RevisionStatus.SUBMITTED,
    RevisionStatus.APPROVED,
    RevisionStatus.REJECTED,
    RevisionStatus.SUPERSEDED,
]

# The only columns the review flow may write once a revision is locked.
# Everything else is evidence of what the technician reported.
REVIEW_COLUMNS = {
    "status", "submitted_at", "reviewed_by", "reviewed_at", "review_notes",
}


class RoofType(models.TextChoices):
    FLAT_RCC = "flat_rcc", "Flat RCC"
    SLOPED_TILE = "sloped_tile", "Sloped tile"
    METAL_SHEET = "metal_sheet", "Metal sheet"
    OTHER = "other", "Other"


class Orientation(models.TextChoices):
    """Which way the roof face points. South is best in India."""

    NORTH = "N", "North"
    NORTH_EAST = "NE", "North-east"
    EAST = "E", "East"
    SOUTH_EAST = "SE", "South-east"
    SOUTH = "S", "South"
    SOUTH_WEST = "SW", "South-west"
    WEST = "W", "West"
    NORTH_WEST = "NW", "North-west"


# ============================================================
# Survey
# ============================================================

class Survey(models.Model):
    """
    The survey for one enquiry, across however many attempts it takes.

    Holds no measurements itself. Everything measured lives on a
    revision, so history is never overwritten.
    """

    enquiry = models.OneToOneField(
        Enquiry, on_delete=models.PROTECT, related_name="survey"
    )
    assigned_to = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
                                    null=True, blank=True, related_name="assigned_surveys")
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"Survey for {self.enquiry.reference}"

    @property
    def latest_revision(self):
        return self.revisions.first()

    @property
    def approved_revision(self):
        """
        The revision a quotation may be built from, or None.

        At most one revision is ever approved, enforced by a database
        constraint on SurveyRevision.
        """
        return self.revisions.filter(status=RevisionStatus.APPROVED).first()

    @property
    def is_approved(self):
        return self.approved_revision is not None


# ============================================================
# Survey revision
# ============================================================

class SurveyRevision(models.Model):
    """
    One recorded attempt at surveying the site.

    Drafts and requested corrections are editable. Each submission is
    retained as an audit snapshot; approval freezes the revision.
    """

    survey = models.ForeignKey(
        Survey, on_delete=models.PROTECT, related_name="revisions"
    )
    revision_number = models.PositiveIntegerField()
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(
        max_length=20,
        choices=RevisionStatus.choices,
        default=RevisionStatus.DRAFT,
    )

    # --- the roof ---
    roof_type = models.CharField(max_length=20, choices=RoofType.choices)
    roof_length_m = models.DecimalField(max_digits=6, decimal_places=2)
    roof_width_m = models.DecimalField(max_digits=6, decimal_places=2)
    usable_area_sqm = models.DecimalField(
        max_digits=8, decimal_places=2,
        help_text="Shadow-free area actually available for panels.",
    )
    orientation = models.CharField(max_length=2, choices=Orientation.choices)
    tilt_degrees = models.DecimalField(
        max_digits=4, decimal_places=1,
        validators=[MinValueValidator(0), MaxValueValidator(90)],
        help_text="0 is flat, 90 is vertical.",
    )
    shading_notes = models.TextField(
        blank=True, help_text="Trees, water tanks, neighbouring buildings."
    )

    # --- the cable run ---
    # Drives cable quantity in F04, so it is measured, not estimated.
    cable_distance_m = models.DecimalField(
        max_digits=6, decimal_places=2,
        help_text="Measured route from array to inverter, not a straight line.",
    )
    cable_route_notes = models.TextField(blank=True)

    # --- access and grid ---
    site_access_notes = models.TextField(
        blank=True, help_text="Stairs, lift, crane needed, parking."
    )
    grid_connection_number = models.CharField(max_length=50, blank=True)
    sanctioned_load_kw = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    grid_suitable = models.BooleanField(default=True)
    grid_notes = models.TextField(blank=True)

    # --- what the technician recommends ---
    recommended_system_type = models.CharField(
        max_length=20, choices=SystemType.choices
    )
    recommended_capacity_kw = models.DecimalField(
        max_digits=5, decimal_places=2,
        help_text="Advisory until approved. Not a certified design.",
    )

    # --- off-grid only ---
    # Battery sizing needs load and backup duration. It can never be
    # inferred from panel capacity, so an off-grid survey must carry
    # both. Enforced in clean().
    critical_load_kw = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True
    )
    backup_duration_hours = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True
    )

    # --- who and when ---
    surveyed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="surveys_carried_out",
    )
    # When the technician was on the roof, which is not when the form
    # was filled in. Both are kept, per spec.md section 6.
    surveyed_at = models.DateTimeField()

    submitted_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="surveys_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    review_notes = models.TextField(
        blank=True, help_text="Required when asking for changes or rejecting."
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-revision_number"]
        constraints = [
            models.UniqueConstraint(
                fields=["survey", "revision_number"],
                name="unique_revision_number_per_survey",
            ),
            # At most one approved revision per survey. A quotation
            # must never have two sources of truth to choose from.
            models.UniqueConstraint(
                fields=["survey"],
                condition=models.Q(status="approved"),
                name="one_approved_revision_per_survey",
            ),
        ]

    def __str__(self):
        return f"{self.survey.enquiry.reference} rev {self.revision_number}"

    @property
    def is_editable(self):
        return self.status in (RevisionStatus.DRAFT, RevisionStatus.CHANGES_REQUESTED)

    def clean(self):
        """Checks that hold however the record is created."""
        if self.recommended_system_type == SystemType.OFF_GRID:
            if self.critical_load_kw is None or self.backup_duration_hours is None:
                raise ValidationError(
                    "An off-grid survey needs the critical load and the "
                    "backup duration. Battery size cannot be guessed from "
                    "panel capacity."
                )

        usable = _as_decimal(self.usable_area_sqm)
        length = _as_decimal(self.roof_length_m)
        width = _as_decimal(self.roof_width_m)

        if usable and length and width and usable > length * width:
            raise ValidationError(
                "Usable area cannot exceed the measured roof area."
            )

    def save(self, *args, **kwargs):
        """Numbers the revision on first insert, then refuses edits."""
        if self.pk:
            self._refuse_edit_if_locked(kwargs.get("update_fields"))
            self.revision += 1
            if kwargs.get("update_fields"):
                kwargs["update_fields"] = [*kwargs["update_fields"], "revision", "updated_at"]
            return super().save(*args, **kwargs)

        # Locks the parent survey, not the revisions: a first revision
        # has no sibling rows to lock, so two at once would both be
        # numbered 1. The second now waits and becomes 2.
        with transaction.atomic():
            Survey.objects.select_for_update().get(pk=self.survey_id)
            last = (
                SurveyRevision.objects.filter(survey=self.survey)
                .order_by("-revision_number")
                .first()
            )
            self.revision_number = (last.revision_number + 1) if last else 1
            return super().save(*args, **kwargs)

    def _refuse_edit_if_locked(self, update_fields):
        """
        Judges by the status in the database, never the one in memory.

        An in-memory status can be stale, or simply changed back to
        draft by the caller, and neither may unlock reviewed evidence.
        """
        stored_status = (
            SurveyRevision.objects.filter(pk=self.pk)
            .values_list("status", flat=True)
            .first()
        )
        if stored_status not in LOCKED_STATUSES:
            return

        is_review_write = update_fields and set(update_fields) <= REVIEW_COLUMNS
        if not is_review_write:
            raise ValidationError(
                f"Revision {self.revision_number} is "
                f"{RevisionStatus(stored_status).label.lower()} and cannot be "
                "edited. Create a new revision instead."
            )

    # --- review flow -------------------------------------------------

    @transaction.atomic
    def submit(self, actor=None):
        """Sends the revision for review."""
        Survey.objects.select_for_update().get(pk=self.survey_id)
        SurveyRevision.objects.select_for_update().get(pk=self.pk)
        self.refresh_from_db()
        self._require_transition(RevisionStatus.SUBMITTED)
        self.full_clean(exclude=["revision_number"])
        before = {"status": self.status}
        self.status = RevisionStatus.SUBMITTED
        self.submitted_at = timezone.now()
        self.save(update_fields=["status", "submitted_at"])
        record_event(self, "submitted", actor or self.surveyed_by, before=before,
                     after={"status": self.status, "measurements": self.measurement_snapshot(),
                            "photo_ids": list(self.photos.values_list("id", flat=True))})

    def measurement_snapshot(self):
        """Retain the submitted evidence before any requested correction."""
        from .serializers import MEASUREMENT_FIELDS
        return {field: str(getattr(self, field)) for field in MEASUREMENT_FIELDS}

    def review(self, decision, reviewer, notes=""):
        """
        Records an approver's decision.

        Approving is what unlocks quotation generation, so only a user
        holding the operations manager or administrator role may do it.
        The same applies to sending one back or rejecting it, which are
        the other half of the same decision. Both of those always carry
        a reason.

        Runs with the survey locked, so two approvals at once cannot
        both see the old revision as the one to replace. The status is
        reread under that lock, because this copy may be out of date.
        """
        with transaction.atomic():
            Survey.objects.select_for_update().get(pk=self.survey_id)
            self.refresh_from_db()
            self._record_decision(decision, reviewer, notes)

    def _record_decision(self, decision, reviewer, notes):
        self._require_transition(decision)

        if not can_approve_surveys(reviewer):
            raise ValidationError(
                "Only an operations manager may review a survey."
            )

        if decision != RevisionStatus.APPROVED and not notes.strip():
            raise ValidationError(
                "Say what is wrong when asking for changes or rejecting."
            )

        if decision == RevisionStatus.APPROVED:
            self._supersede_current_approval(reviewer)

        previous_status = self.status
        self.status = decision
        self.reviewed_by = reviewer
        self.reviewed_at = timezone.now()
        self.review_notes = notes.strip()
        self.save(
            update_fields=["status", "reviewed_by", "reviewed_at", "review_notes"]
        )
        record_event(self, "reviewed", reviewer, before={"status": previous_status},
                     after={"status": decision}, reason=notes)

    def _supersede_current_approval(self, reviewer):
        """Ends the approval this revision replaces, if there is one."""
        current = self.survey.revisions.filter(status=RevisionStatus.APPROVED).first()
        if current:
            current.status = RevisionStatus.SUPERSEDED
            current.save(update_fields=["status"])
            record_event(current, "superseded", reviewer,
                         before={"status": RevisionStatus.APPROVED},
                         after={"status": RevisionStatus.SUPERSEDED})

    def _require_transition(self, target):
        if target not in ALLOWED_REVISION_CHANGES.get(self.status, []):
            raise ValidationError(
                f"Cannot move a {self.get_status_display().lower()} revision "
                f"to {RevisionStatus(target).label.lower()}."
            )


# ============================================================
# Photos
# ============================================================

class SurveyPhoto(models.Model):
    """Evidence attached to one revision."""

    revision = models.ForeignKey(
        SurveyRevision, on_delete=models.PROTECT, related_name="photos"
    )
    image = models.ImageField(upload_to="survey_photos/")
    caption = models.CharField(max_length=200, blank=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.caption or f"Photo {self.id}"


# ============================================================
# Helpers
# ============================================================

def _as_decimal(value):
    """
    Converts a field value to Decimal, or None if it is not a number.

    clean() may run before Django has converted the field, for example
    when a serializer validates an unsaved instance, so the value can
    still be the string that arrived in the request.
    """
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


# ============================================================
# Permissions
# ============================================================

def can_approve_surveys(user):
    """
    Approval gates every quotation, so it is restricted.

    Per the permission matrix in rules.md section 4, survey approval
    belongs to the operations manager.
    """
    from apps.accounts.models import Role

    return user.has_any_role(Role.OPERATIONS_MANAGER)
