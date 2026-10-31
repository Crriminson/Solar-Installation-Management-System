"""
Installation evidence operations for F11.

Submission freezes the document the customer will be shown, and
acceptance has to quote the revision that was on the screen. Without
that, a crew could correct a report between the customer reading it and
signing it, and the signature would belong to a document nobody saw.
"""

from django.db import models, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from apps.core.api import check_revision
from apps.core.models import record_event
from apps.inventory.models import MovementReason, SerializedUnit, StockStatus
from apps.inventory.services import move_stock
from apps.orders.models import Order, OrderStatus
from apps.quotations.services import content_hash
from apps.scheduling.models import Job, JobKind, JobStatus
from apps.scheduling.services import move_job

from .models import (Decision, InstallationAcceptance, InstallationReport, InstalledUnit,
                     ReportStatus)


# ============================================================
# The report
# ============================================================

@transaction.atomic
def open_report(job_id, actor):
    """Starts the on-site form. One per installation job."""
    job = Job.objects.select_for_update().filter(pk=job_id).first()
    if job is None:
        raise NotFound()

    existing = InstallationReport.objects.filter(job=job).first()
    if existing is not None:
        return existing

    if job.kind != JobKind.INSTALLATION:
        raise ValidationError(
            {"job": ["Only an installation job has an installation report."]}
        )
    if job.status != JobStatus.IN_PROGRESS:
        raise ValidationError(
            {"job": ["Start the job before recording what was installed."]}
        )

    report = InstallationReport.objects.create(job=job, created_by=actor)
    record_event(report, "opened", actor, after={"job": job.pk})
    return report


@transaction.atomic
def update_report(report_id, data, actor):
    """Saves the crew's measurements while the report is still open."""
    report = _locked_report(report_id)
    check_revision(report, data)

    if not report.is_editable:
        raise ValidationError(
            {"status": [f"A {report.get_status_display().lower()} report cannot be edited."]}
        )

    started = data.get("started_at", report.started_at)
    finished = data.get("finished_at", report.finished_at)
    if started and finished and finished <= started:
        raise ValidationError(
            {"finished_at": ["The work cannot have finished before it started."]}
        )
    if finished and finished > timezone.now():
        raise ValidationError({"finished_at": ["That is in the future."]})

    fields = {name: value for name, value in data.items() if name != "revision"}
    _update(report, actor, "updated", **fields)
    return report


@transaction.atomic
def add_installed_unit(report_id, data, actor):
    """
    Records one serial as fitted at this site.

    The unit has to have reached the customer on this job's order. A
    serial that was never delivered here cannot be on this roof, and
    letting it through would corrupt the warranty record (F12).
    """
    report = _locked_report(report_id)
    if not report.is_editable:
        raise ValidationError({"status": ["This report is closed."]})

    code = data["code"].strip()
    unit = SerializedUnit.objects.select_for_update().filter(
        models.Q(serial_number=code) | models.Q(asset_id=code)
    ).first()
    if unit is None:
        raise ValidationError({"code": [f"No unit matches {code}."]})

    order = report.job.order
    if order is not None and unit.order_id != order.pk:
        raise ValidationError(
            {"code": [f"{unit.asset_id} was not delivered on {order.reference}."]}
        )
    if unit.status != StockStatus.DELIVERED:
        raise ValidationError({"code": [
            f"{unit.asset_id} is {unit.get_status_display().lower()}, not delivered."
        ]})
    if InstalledUnit.objects.filter(report=report, unit=unit).exists():
        raise ValidationError({"code": [f"{unit.asset_id} is already on this report."]})

    entry = InstalledUnit.objects.create(
        report=report, unit=unit, position_note=data.get("position_note", "").strip()
    )
    record_event(entry, "installed_unit_recorded", actor, after={"asset": unit.asset_id})
    return entry


@transaction.atomic
def submit_report(report_id, data, actor):
    """
    Freezes the report and puts the job in front of the customer.

    Refused outright while any required evidence is missing: an
    installation signed off without a generation test result is not
    evidence of a working system.
    """
    report = _locked_report(report_id)
    check_revision(report, data)

    if not report.is_editable:
        raise ValidationError({"status": ["This report has already been submitted."]})

    missing = report.missing_evidence()
    if missing:
        raise ValidationError({"evidence": [
            "Still needed before the customer can sign: " + "; ".join(missing) + "."
        ]})

    digest = content_hash(document_content(report))
    _update(report, actor, "submitted", status=ReportStatus.SUBMITTED,
            submitted_at=timezone.now(), content_hash=digest)

    job = Job.objects.select_for_update().get(pk=report.job_id)
    if job.status == JobStatus.IN_PROGRESS:
        move_job(job, JobStatus.AWAITING_ACCEPTANCE, actor)
    return report


def document_content(report):
    """The fields the content hash covers: everything the customer reads."""
    return {
        "job": report.job_id,
        "started_at": str(report.started_at),
        "finished_at": str(report.finished_at),
        "system_type": report.system_type,
        "installed_capacity_kw": str(report.installed_capacity_kw),
        "checklist": report.checklist,
        "generation_test_kw": str(report.generation_test_kw),
        "generation_test_passed": report.generation_test_passed,
        "notes": report.notes,
        "units": sorted(
            entry.unit.asset_id for entry in report.installed_units.select_related("unit")
        ),
        "photos": sorted(photo.caption for photo in report.photos.all()),
    }


# ============================================================
# Acceptance
# ============================================================

@transaction.atomic
def decide(report_id, data, actor):
    """
    Records the customer's decision on the revision they were shown.

    A refusal is a real outcome: the work stays open with the reason,
    the crew goes back, and nothing about the installation is marked
    complete.
    """
    report = _locked_report(report_id)

    if report.status != ReportStatus.SUBMITTED:
        raise ValidationError(
            {"status": ["Submit the report before asking the customer to sign."]}
        )
    if data["document_revision"] != report.revision:
        raise ValidationError({"document_revision": [
            "This report changed since it was shown. Read the new version to the "
            "customer before they decide."
        ]})
    if content_hash(document_content(report)) != report.content_hash:
        raise ValidationError({"document": [
            "The report no longer matches what was submitted."
        ]})

    decision = data["decision"]
    if decision == Decision.ACCEPTED:
        _accept(report, data, actor)
    else:
        _refuse(report, data, actor)

    return InstallationAcceptance.objects.get(report=report)


def _accept(report, data, actor):
    if not data.get("signature"):
        raise ValidationError({"signature": ["The customer signs to accept."]})

    InstallationAcceptance.objects.create(
        report=report, decision=Decision.ACCEPTED,
        customer_name=data["customer_name"], signature=data["signature"],
        document_revision=report.revision, document_content_hash=report.content_hash,
        witnessed_by=actor, decided_at=timezone.now(),
    )
    _update(report, actor, "accepted", status=ReportStatus.ACCEPTED)

    # The serials are now on a roof, not in a van. Their warranties
    # started at delivery (F12), so acceptance changes nothing about cover.
    for entry in report.installed_units.select_related("unit"):
        move_stock(actor, unit=entry.unit, to_status=StockStatus.INSTALLED,
                   reason=MovementReason.INSTALLATION, order=report.job.order)

    job = Job.objects.select_for_update().get(pk=report.job_id)
    move_job(job, JobStatus.COMPLETED, actor, reason="Customer accepted the installation.")

    order = report.job.order
    if order is not None:
        Order.objects.filter(pk=order.pk, status=OrderStatus.DELIVERED).update(
            status=OrderStatus.COMPLETED, revision=order.revision + 1
        )


def _refuse(report, data, actor):
    reason = data.get("refusal_reason", "").strip()
    if not reason:
        raise ValidationError(
            {"refusal_reason": ["Record what the customer is unhappy with."]}
        )

    InstallationAcceptance.objects.create(
        report=report, decision=Decision.REFUSED,
        customer_name=data["customer_name"], refusal_reason=reason,
        document_revision=report.revision, document_content_hash=report.content_hash,
        witnessed_by=actor, decided_at=timezone.now(),
    )
    _update(report, actor, "refused", status=ReportStatus.REFUSED, reason=reason)

    # The work is not finished, so the job goes back to the crew.
    job = Job.objects.select_for_update().get(pk=report.job_id)
    move_job(job, JobStatus.IN_PROGRESS, actor, reason=f"Customer refused: {reason}")


# ============================================================
# Helpers
# ============================================================

def _locked_report(report_id):
    # of=("self",): job.order is nullable, and PostgreSQL will not take
    # FOR UPDATE on the nullable side of an outer join.
    report = (InstallationReport.objects.select_for_update(of=("self",))
              .select_related("job__order")
              .filter(pk=report_id).first())
    if report is None:
        raise NotFound()
    return report


def _update(report, actor, action, *, reason="", **fields):
    before = {"status": report.status, "revision": report.revision}
    InstallationReport.objects.filter(pk=report.pk).update(
        revision=report.revision + 1, updated_at=timezone.now(), **fields
    )
    report.refresh_from_db()
    record_event(report, action, actor, before=before,
                 after={"status": report.status, "revision": report.revision},
                 reason=reason)
