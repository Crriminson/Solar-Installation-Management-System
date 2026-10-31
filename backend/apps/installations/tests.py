"""
F11 - what installation evidence has to prove.

A signature is only worth something if it is attached to the exact
report the customer read, and a report is only evidence if it cannot be
submitted with the proof missing. Refusal is a real outcome, so it is
tested as one rather than as an error.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.fulfilment.tests import FulfilmentTestCase
from apps.inventory.models import SerializedUnit, StockStatus
from apps.orders.models import OrderStatus
from apps.quotations.test_acceptance import signature_file
from apps.scheduling.models import Job, JobKind, JobStatus

from .models import (Decision, InstallationAcceptance, InstallationPhoto,
                     InstallationReport, MANDATORY_CHECKS, ReportStatus)

User = get_user_model()
JSON = "application/json"


class InstallationTestCase(FulfilmentTestCase):
    """Carries the order all the way to delivered, then books the fitting."""

    def setUp(self):
        super().setUp()
        self.deliver_the_order()

        self.crew = User.objects.create_user("crew", roles=[Role.TECHNICIAN])
        self.ops = User.objects.create_user("inst_ops", roles=[Role.OPERATIONS_MANAGER])

        self.client.force_login(self.ops)
        starts_at = timezone.now() + timedelta(hours=1)
        self.client.post(reverse("job-create"), {
            "kind": JobKind.INSTALLATION, "site": self.order.site_id,
            "order": self.order.pk,
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at + timedelta(hours=6)).isoformat(),
            "technicians": [self.crew.pk],
        }, content_type=JSON)
        self.job = Job.objects.get()

    def deliver_the_order(self):
        fulfilment = self.stock_everything()
        self.reserve(fulfilment)
        self.scan_everything(fulfilment)
        fulfilment.refresh_from_db()

        self.client.force_login(self.warehouse)
        self.client.post(reverse("fulfilment-close", args=[fulfilment.pk]),
                         {"revision": fulfilment.revision}, content_type=JSON)
        fulfilment.refresh_from_db()
        self.client.post(reverse("fulfilment-dispatch", args=[fulfilment.pk]),
                         {"revision": fulfilment.revision}, content_type=JSON)
        fulfilment.refresh_from_db()
        self.client.post(reverse("fulfilment-deliver", args=[fulfilment.pk]),
                         {"revision": fulfilment.revision,
                          "delivered_at": timezone.now().isoformat(),
                          "received_by_name": "Ramesh Gupta"}, content_type=JSON)

    # --- helpers -------------------------------------------------------

    def start_the_job(self):
        self.client.force_login(self.ops)
        self.job.refresh_from_db()
        return self.client.post(reverse("job-action", args=[self.job.pk, "start"]),
                                {"revision": self.job.revision}, content_type=JSON)

    def open_report(self):
        self.start_the_job()
        self.client.force_login(self.crew)
        response = self.client.post(reverse("installation-open"),
                                    {"job": self.job.pk}, content_type=JSON)
        return InstallationReport.objects.get(pk=response.json()["id"])

    def fill_in(self, report, **changes):
        report.refresh_from_db()
        payload = {
            "revision": report.revision,
            "started_at": (timezone.now() - timedelta(hours=5)).isoformat(),
            "finished_at": (timezone.now() - timedelta(hours=1)).isoformat(),
            "system_type": "on_grid",
            "installed_capacity_kw": "3.00",
            "checklist": [{"item": check, "passed": True} for check in MANDATORY_CHECKS],
            "generation_test_kw": "2.80",
            "generation_test_passed": True,
            **changes,
        }
        return self.client.post(reverse("installation-update", args=[report.pk]),
                                payload, content_type=JSON)

    def add_evidence(self, report):
        for unit in SerializedUnit.objects.filter(
                order=self.order, status=StockStatus.DELIVERED)[:2]:
            self.client.post(reverse("installation-units", args=[report.pk]),
                             {"code": unit.asset_id}, content_type=JSON)
        self.client.post(reverse("installation-photos", args=[report.pk]),
                         {"image": signature_file("roof.png"),
                          "caption": "Finished array from the south"})

    def complete_report(self):
        report = self.open_report()
        self.fill_in(report)
        self.add_evidence(report)
        report.refresh_from_db()
        return report

    def submit(self, report):
        report.refresh_from_db()
        return self.client.post(reverse("installation-submit", args=[report.pk]),
                                {"revision": report.revision}, content_type=JSON)


class ReportTests(InstallationTestCase):
    def test_the_form_opens_once_the_crew_is_on_site(self):
        report = self.open_report()

        self.assertEqual(report.status, ReportStatus.DRAFT)

    def test_the_form_does_not_open_before_the_job_starts(self):
        self.client.force_login(self.crew)

        response = self.client.post(reverse("installation-open"),
                                    {"job": self.job.pk}, content_type=JSON)

        self.assertEqual(response.status_code, 400)

    def test_finishing_before_starting_is_refused(self):
        report = self.open_report()

        response = self.fill_in(
            report,
            started_at=timezone.now().isoformat(),
            finished_at=(timezone.now() - timedelta(hours=2)).isoformat(),
        )

        self.assertEqual(response.status_code, 400)

    def test_a_serial_that_was_never_delivered_here_is_refused(self):
        report = self.open_report()

        response = self.client.post(reverse("installation-units", args=[report.pk]),
                                    {"code": "NOT-DELIVERED-HERE"}, content_type=JSON)

        self.assertEqual(response.status_code, 400)


class SubmissionTests(InstallationTestCase):
    def test_submitting_without_the_evidence_is_refused(self):
        report = self.open_report()
        self.fill_in(report)

        response = self.submit(report)

        self.assertEqual(response.status_code, 400)
        self.assertIn("Still needed", str(response.content))

    def test_the_form_says_what_is_still_missing(self):
        report = self.open_report()

        body = self.client.get(reverse("installation-detail", args=[report.pk])).json()

        self.assertTrue(body["missing_evidence"])

    def test_a_complete_report_submits_and_waits_on_the_customer(self):
        report = self.complete_report()

        response = self.submit(report)

        self.assertEqual(response.status_code, 200, response.content)
        report.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(report.status, ReportStatus.SUBMITTED)
        self.assertTrue(report.content_hash)
        self.assertEqual(self.job.status, JobStatus.AWAITING_ACCEPTANCE)

    def test_a_submitted_report_cannot_be_edited(self):
        report = self.complete_report()
        self.submit(report)

        response = self.fill_in(report, notes="Changed my mind")

        self.assertEqual(response.status_code, 400)


class AcceptanceTests(InstallationTestCase):
    def setUp(self):
        super().setUp()
        self.report = self.complete_report()
        self.submit(self.report)
        self.report.refresh_from_db()

    def decide(self, decision, revision=None, **extra):
        return self.client.post(
            reverse("installation-decide", args=[self.report.pk]),
            {"decision": decision,
             "document_revision": revision or self.report.revision,
             "customer_name": "Ramesh Gupta", **extra},
        )

    def test_accepting_completes_the_job_and_puts_the_kit_on_the_roof(self):
        response = self.decide(Decision.ACCEPTED, signature=signature_file())

        self.assertEqual(response.status_code, 201, response.content)
        self.report.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(self.report.status, ReportStatus.ACCEPTED)
        self.assertEqual(self.job.status, JobStatus.COMPLETED)

        fitted = self.report.installed_units.first().unit
        fitted.refresh_from_db()
        self.assertEqual(fitted.status, StockStatus.INSTALLED)

        self.order.refresh_from_db()
        self.assertEqual(self.order.status, OrderStatus.COMPLETED)

    def test_signing_for_a_different_revision_is_refused(self):
        response = self.decide(Decision.ACCEPTED, revision=self.report.revision + 1,
                               signature=signature_file())

        self.assertEqual(response.status_code, 400)
        self.assertIn("changed since it was shown", str(response.content))
        self.assertFalse(InstallationAcceptance.objects.exists())

    def test_accepting_without_a_signature_is_refused(self):
        response = self.decide(Decision.ACCEPTED)

        self.assertEqual(response.status_code, 400)

    def test_refusal_is_a_valid_outcome_and_leaves_the_work_open(self):
        response = self.decide(Decision.REFUSED,
                               refusal_reason="Cable run along the front wall is untidy")

        self.assertEqual(response.status_code, 201, response.content)
        self.report.refresh_from_db()
        self.job.refresh_from_db()
        self.assertEqual(self.report.status, ReportStatus.REFUSED)
        self.assertEqual(self.job.status, JobStatus.IN_PROGRESS)
        self.assertIn("untidy", InstallationAcceptance.objects.get().refusal_reason)
        self.order.refresh_from_db()
        self.assertNotEqual(self.order.status, OrderStatus.COMPLETED)

    def test_refusing_without_saying_why_is_refused(self):
        response = self.decide(Decision.REFUSED)

        self.assertEqual(response.status_code, 400)

    def test_acceptance_evidence_cannot_be_edited_or_deleted(self):
        self.decide(Decision.ACCEPTED, signature=signature_file())
        acceptance = InstallationAcceptance.objects.get()

        acceptance.customer_name = "Somebody Else"
        with self.assertRaises(ValidationError):
            acceptance.save()
        with self.assertRaises(ValidationError):
            acceptance.delete()

    def test_a_refused_report_can_be_corrected_and_resubmitted(self):
        self.decide(Decision.REFUSED, refusal_reason="Untidy cable run")

        self.report.refresh_from_db()
        fixed = self.fill_in(self.report, notes="Cable re-run behind the downpipe")

        self.assertEqual(fixed.status_code, 200, fixed.content)
