"""
F10 - scheduling technicians onto work.

    Job            - a visit: a survey, an installation or a service call.
    JobAssignment  - one technician on that job. A job may have a team.
    ScheduleChange - the previous slot, kept whenever a job is moved.

Two rules shape everything here. A technician cannot be in two places
at once, so overlapping active assignments are rejected. And a job that
moves keeps its history, because "when was this originally booked for"
is the first question asked when a customer complains about a delay.

Confirming an order creates its installation job before anyone has
picked a date (spec.md F07). That job waits with no slot and no crew
rather than an invented appointment; the database holds both halves of
that rule, so a waiting job can never carry a time and a booked one can
never lack one.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


# ============================================================
# Choices
# ============================================================

class JobKind(models.TextChoices):
    SURVEY = "survey", "Site survey"
    INSTALLATION = "installation", "Installation"
    SERVICE = "service", "Service visit"


class JobStatus(models.TextChoices):
    AWAITING_SCHEDULING = "awaiting_scheduling", "Awaiting scheduling"
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    AWAITING_ACCEPTANCE = "awaiting_acceptance", "Awaiting customer acceptance"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


ALLOWED_JOB_MOVES = {
    # Booking is the only way on: a waiting job cannot be started.
    JobStatus.AWAITING_SCHEDULING: [JobStatus.SCHEDULED, JobStatus.CANCELLED],
    JobStatus.SCHEDULED: [JobStatus.IN_PROGRESS, JobStatus.CANCELLED],
    JobStatus.IN_PROGRESS: [JobStatus.AWAITING_ACCEPTANCE, JobStatus.CANCELLED],
    # Acceptance is F11's to record, and a refusal sends the crew back.
    JobStatus.AWAITING_ACCEPTANCE: [JobStatus.COMPLETED, JobStatus.IN_PROGRESS],
    JobStatus.COMPLETED: [],
    JobStatus.CANCELLED: [],
}

# A technician booked in one of these is not free for another job. A job
# awaiting scheduling has no slot and no crew, so it holds nobody.
ACTIVE_STATUSES = [JobStatus.SCHEDULED, JobStatus.IN_PROGRESS,
                   JobStatus.AWAITING_ACCEPTANCE]


# ============================================================
# Job
# ============================================================

class Job(models.Model):
    """One visit, with a team and a slot."""

    kind = models.CharField(max_length=20, choices=JobKind.choices)
    status = models.CharField(
        max_length=25, choices=JobStatus.choices, default=JobStatus.SCHEDULED
    )
    site = models.ForeignKey("customers.Site", on_delete=models.PROTECT,
                             related_name="jobs")

    # An installation hangs off an order; a survey does not. Both are
    # optional so a service visit can exist against neither.
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, null=True, blank=True,
        related_name="jobs",
    )
    survey = models.ForeignKey(
        "surveys.Survey", on_delete=models.PROTECT, null=True, blank=True,
        related_name="jobs",
    )

    # A service visit belongs to its ticket. A ticket may need several.
    ticket = models.ForeignKey(
        "support.ServiceTicket", on_delete=models.PROTECT, null=True, blank=True,
        related_name="jobs",
    )

    # Empty only while the job awaits scheduling; see the constraint below.
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    # Delays are recorded against somebody, so a blocked job has an owner
    # rather than drifting unowned.
    blocked_reason = models.TextField(blank=True)
    blocked_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="blocked_jobs",
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="jobs_created"
    )
    cancelled_reason = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["starts_at", "id"]
        indexes = [models.Index(fields=["status", "starts_at"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(ends_at__gt=models.F("starts_at")),
                name="job_ends_after_it_starts",
            ),
            models.CheckConstraint(
                condition=~models.Q(blocked_reason="") | models.Q(blocked_owner__isnull=True),
                name="blocked_job_has_an_owner",
            ),
            # No invented dates: a waiting job has no slot, and every other
            # job has a whole one. A job cancelled before it was ever booked
            # keeps having none.
            models.CheckConstraint(
                condition=(
                    models.Q(status__in=[JobStatus.AWAITING_SCHEDULING, JobStatus.CANCELLED],
                             starts_at__isnull=True, ends_at__isnull=True)
                    | (~models.Q(status=JobStatus.AWAITING_SCHEDULING)
                       & models.Q(starts_at__isnull=False, ends_at__isnull=False))
                ),
                name="job_has_a_slot_unless_awaiting_scheduling",
            ),
            # Spec.md F07: one installation per order. A cancelled one is
            # history, so a replacement may follow it.
            models.UniqueConstraint(
                fields=["order"],
                condition=(models.Q(kind=JobKind.INSTALLATION)
                           & ~models.Q(status=JobStatus.CANCELLED)),
                name="one_open_installation_per_order",
            ),
        ]

    def __str__(self):
        when = f"{self.starts_at:%Y-%m-%d}" if self.starts_at else "not yet booked"
        return f"{self.get_kind_display()} at {self.site}, {when}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Jobs are cancelled, never deleted.")

    @property
    def is_blocked(self):
        return bool(self.blocked_reason)

    @property
    def technicians(self):
        return [assignment.technician for assignment in self.assignments.all()]


# ============================================================
# Assignment
# ============================================================

class JobAssignment(models.Model):
    """
    One technician on one job.

    Overlap is checked in the service with the technician's row locked,
    because "is this person free" is a question about other rows and no
    single-row constraint can answer it.
    """

    job = models.ForeignKey(Job, on_delete=models.PROTECT, related_name="assignments")
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="job_assignments"
    )
    is_lead = models.BooleanField(default=False)
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-is_lead", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["job", "technician"],
                name="one_assignment_per_technician_per_job",
            ),
            models.UniqueConstraint(
                fields=["job"], condition=models.Q(is_lead=True),
                name="one_lead_per_job",
            ),
        ]

    def __str__(self):
        return f"{self.technician} on job {self.job_id}"


# ============================================================
# Schedule history
# ============================================================

class ScheduleChange(models.Model):
    """The slot a job used to hold, kept whenever it moves."""

    job = models.ForeignKey(Job, on_delete=models.PROTECT, related_name="schedule_changes")
    previous_starts_at = models.DateTimeField()
    previous_ends_at = models.DateTimeField()
    reason = models.TextField()
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="reschedules"
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at", "-id"]

    def __str__(self):
        return f"Job {self.job_id} moved from {self.previous_starts_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Schedule history is append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Schedule history cannot be deleted.")
