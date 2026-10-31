"""
Scheduling operations for F10.

The overlap check is the reason this is a service and not a model
method. "Is this technician free?" is a question about other rows, so
it needs the technician's row locked first: two schedulers booking the
same person into the same hour must not both read an empty diary.
"""

from django.contrib.auth import get_user_model
from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.accounts.models import Role
from apps.core.api import check_revision
from apps.core.models import record_event
from apps.customers.models import Site
from apps.fulfilment.models import FulfilmentStatus
from apps.orders.models import Order

from .models import (ACTIVE_STATUSES, ALLOWED_JOB_MOVES, Job, JobAssignment, JobKind,
                     JobStatus, ScheduleChange)

User = get_user_model()


# ============================================================
# Creating and staffing a job
# ============================================================

@transaction.atomic
def create_job(data, actor):
    """Books a visit and staffs it, refusing any technician already out."""
    site = Site.objects.filter(pk=data["site"]).first()
    if site is None:
        raise ValidationError({"site": ["No site with that id."]})

    if data["ends_at"] <= data["starts_at"]:
        raise ValidationError({"ends_at": ["A job has to end after it starts."]})

    order = None
    if data.get("order"):
        order = Order.objects.filter(pk=data["order"]).first()
        if order is None:
            raise ValidationError({"order": ["No order with that id."]})

    job = Job.objects.create(
        kind=data["kind"],
        site=site,
        order=order,
        survey_id=data.get("survey"),
        ticket_id=data.get("ticket"),
        starts_at=data["starts_at"],
        ends_at=data["ends_at"],
        notes=data.get("notes", "").strip(),
        created_by=actor,
    )

    for index, technician_id in enumerate(data["technicians"]):
        assign_technician(job, technician_id, actor, is_lead=(index == 0))

    record_event(job, "scheduled", actor,
                 after={"kind": job.kind, "starts_at": str(job.starts_at)})
    return job


def assign_technician(job, technician_id, actor, *, is_lead=False):
    """
    Puts one technician on a job, if they are free for that whole slot.

    Locks the technician first, so a second scheduler asking the same
    question at the same moment waits rather than reading a stale diary.
    """
    technician = User.objects.select_for_update().filter(pk=technician_id).first()
    if technician is None:
        raise ValidationError({"technicians": ["No such staff member."]})
    if not technician.has_any_role(Role.TECHNICIAN, Role.OPERATIONS_MANAGER):
        raise ValidationError(
            {"technicians": [f"{technician} is not a technician."]}
        )

    clash = _clashing_job(technician, job.starts_at, job.ends_at, exclude=job.pk)
    if clash is not None:
        raise ValidationError({"technicians": [
            f"{technician} is already on {clash.get_kind_display().lower()} "
            f"{clash.pk} from {timezone.localtime(clash.starts_at):%d %b %H:%M} "
            f"to {timezone.localtime(clash.ends_at):%H:%M}."
        ]})

    return JobAssignment.objects.create(job=job, technician=technician, is_lead=is_lead)


def _clashing_job(technician, starts_at, ends_at, *, exclude=None):
    """
    The first active job this technician holds that overlaps the slot.

    Two intervals overlap when each starts before the other ends. Touching
    at an endpoint is not an overlap: a job ending at 11:00 and the next
    starting at 11:00 is a normal back-to-back day.
    """
    queryset = (Job.objects
                .filter(assignments__technician=technician, status__in=ACTIVE_STATUSES)
                .filter(starts_at__lt=ends_at, ends_at__gt=starts_at))
    if exclude is not None:
        queryset = queryset.exclude(pk=exclude)
    return queryset.first()


# ============================================================
# Moving and blocking
# ============================================================

@transaction.atomic
def reschedule_job(job_id, data, actor):
    """Moves a job, keeping the slot it used to hold and why it moved."""
    job = _locked_job(job_id)
    check_revision(job, data)

    if job.status in (JobStatus.COMPLETED, JobStatus.CANCELLED):
        raise ValidationError(
            {"status": [f"A {job.get_status_display().lower()} job is not rescheduled."]}
        )
    if not data.get("reason", "").strip():
        raise ValidationError({"reason": ["Say why the job is moving."]})
    if data["ends_at"] <= data["starts_at"]:
        raise ValidationError({"ends_at": ["A job has to end after it starts."]})

    for assignment in job.assignments.select_related("technician"):
        technician = User.objects.select_for_update().get(pk=assignment.technician_id)
        clash = _clashing_job(technician, data["starts_at"], data["ends_at"],
                              exclude=job.pk)
        if clash is not None:
            raise ValidationError({"starts_at": [
                f"{technician} is already booked then, on job {clash.pk}."
            ]})

    ScheduleChange.objects.create(
        job=job, previous_starts_at=job.starts_at, previous_ends_at=job.ends_at,
        reason=data["reason"].strip(), changed_by=actor,
    )
    _update(job, actor, "rescheduled", reason=data["reason"],
            starts_at=data["starts_at"], ends_at=data["ends_at"])
    return job


@transaction.atomic
def block_job(job_id, data, actor):
    """Records a delay against somebody, so it is owned rather than drifting."""
    job = _locked_job(job_id)
    check_revision(job, data)

    if not data.get("reason", "").strip():
        raise ValidationError({"reason": ["Say what is holding the job up."]})

    owner = User.objects.filter(pk=data.get("owner")).first()
    if owner is None:
        raise ValidationError({"owner": ["Name who is going to clear this."]})

    _update(job, actor, "blocked", reason=data["reason"],
            blocked_reason=data["reason"].strip(), blocked_owner=owner)
    return job


# ============================================================
# Progress
# ============================================================

@transaction.atomic
def start_job(job_id, data, actor):
    """
    Marks the crew as on site.

    An installation cannot start before its materials are recorded as
    delivered: sending a crew to a roof with nothing to fit is the exact
    wasted trip this system exists to stop.
    """
    job = _locked_job(job_id)
    check_revision(job, data)
    _require_move(job, JobStatus.IN_PROGRESS)

    if job.kind == JobKind.INSTALLATION:
        _require_delivered_materials(job)

    _update(job, actor, "started", status=JobStatus.IN_PROGRESS,
            blocked_reason="", blocked_owner=None)
    return job


def _require_delivered_materials(job):
    if job.order_id is None:
        raise ValidationError(
            {"order": ["An installation needs the order whose materials it fits."]}
        )
    fulfilment = getattr(job.order, "fulfilment", None)
    if fulfilment is None or fulfilment.status != FulfilmentStatus.DELIVERED:
        raise ValidationError({"order": [
            "The materials for this order are not recorded as delivered yet."
        ]})


@transaction.atomic
def cancel_job(job_id, data, actor):
    job = _locked_job(job_id)
    check_revision(job, data)
    _require_move(job, JobStatus.CANCELLED)

    if not data.get("reason", "").strip():
        raise ValidationError({"reason": ["Say why the visit is cancelled."]})

    _update(job, actor, "cancelled", reason=data["reason"],
            status=JobStatus.CANCELLED, cancelled_reason=data["reason"].strip())
    return job


def move_job(job, status, actor, *, reason=""):
    """Used by F11 when evidence is submitted and when the customer signs."""
    _require_move(job, status)
    _update(job, actor, status, reason=reason, status=status)


def begin_visit(job, actor):
    """Used by F13: recording a diagnosis means the technician is there."""
    if job.status == JobStatus.SCHEDULED:
        _update(job, actor, "started", status=JobStatus.IN_PROGRESS,
                blocked_reason="", blocked_owner=None)


def finish_visit(job, actor):
    """
    Ends a service visit, which has no acceptance step of its own.

    The customer's say on a repair is the ticket's confirmation (F13), so
    this skips Awaiting Customer Acceptance, and only for a service visit.
    """
    if job.kind == JobKind.SERVICE and job.status == JobStatus.IN_PROGRESS:
        _update(job, actor, "completed", status=JobStatus.COMPLETED)


# ============================================================
# Helpers
# ============================================================

def _locked_job(job_id):
    # of=("self",) because order is nullable: PostgreSQL refuses FOR
    # UPDATE on the nullable side of the join it produces.
    job = (Job.objects.select_for_update(of=("self",))
           .select_related("site", "order")
           .filter(pk=job_id).first())
    if job is None:
        raise NotFound()
    return job


def _require_move(job, target):
    if target not in ALLOWED_JOB_MOVES.get(job.status, []):
        raise ValidationError({"status": [
            f"A {job.get_status_display().lower()} job cannot become "
            f"{JobStatus(target).label.lower()}."
        ]})


def _update(job, actor, action, *, reason="", **fields):
    before = {"status": job.status, "revision": job.revision}
    Job.objects.filter(pk=job.pk).update(
        revision=job.revision + 1, updated_at=timezone.now(), **fields
    )
    job.refresh_from_db()
    record_event(job, action, actor, before=before,
                 after={"status": job.status, "revision": job.revision}, reason=reason)
