"""
F10 - scheduling technicians onto work.

    Job            - a visit: a survey, an installation or a service call.
    JobAssignment  - one technician on that job. A job may have a team.
    ScheduleChange - the previous slot, kept whenever a job is moved.

Two rules shape everything here. A technician cannot be in two places
at once, so overlapping active assignments are rejected. And a job that
moves keeps its history, because "when was this originally booked for"
is the first question asked when a customer complains about a delay.
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
    SCHEDULED = "scheduled", "Scheduled"
    IN_PROGRESS = "in_progress", "In progress"
    AWAITING_ACCEPTANCE = "awaiting_acceptance", "Awaiting customer acceptance"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


ALLOWED_JOB_MOVES = {
    JobStatus.SCHEDULED: [JobStatus.IN_PROGRESS, JobStatus.CANCELLED],
    JobStatus.IN_PROGRESS: [JobStatus.AWAITING_ACCEPTANCE, JobStatus.CANCELLED],
    # Acceptance is F11's to record, and a refusal sends the crew back.
    JobStatus.AWAITING_ACCEPTANCE: [JobStatus.COMPLETED, JobStatus.IN_PROGRESS],
    JobStatus.COMPLETED: [],
    JobStatus.CANCELLED: [],
}

# A technician booked in one of these is not free for another job.
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

    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
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
        ]

    def __str__(self):
        return f"{self.get_kind_display()} at {self.site} on {self.starts_at:%Y-%m-%d}"

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
