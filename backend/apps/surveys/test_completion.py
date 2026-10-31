"""F03 completion: assigned-only records, correction/resubmission, immutable submission evidence and stale edits."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.models import AuditEvent
from .models import Survey, SurveyRevision
from .test_api_rules import make_enquiry, revision_body
from .tests import make_revision

User = get_user_model()
JSON = "application/json"


class SurveyCompletionTests(TestCase):
    def setUp(self):
        self.technician = User.objects.create_user("assigned", roles=[Role.TECHNICIAN])
        self.other = User.objects.create_user("other", roles=[Role.TECHNICIAN])
        self.manager = User.objects.create_user("manager", roles=[Role.OPERATIONS_MANAGER])
        self.survey = Survey.objects.create(enquiry=make_enquiry(), assigned_to=self.technician)
        self.revision = make_revision(self.survey, self.technician)
        self.client.force_login(self.technician)

    def test_other_technician_cannot_list_read_capture_or_submit(self):
        self.client.force_login(self.other)
        self.assertEqual(self.client.get(reverse("survey-list")).json()["count"], 0)
        self.assertEqual(self.client.get(reverse("survey-detail", args=[self.survey.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("revision-activity", args=[self.revision.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("revision-create", args=[self.survey.pk]), revision_body(), content_type=JSON).status_code, 404)
        self.assertEqual(self.client.post(reverse("revision-submit", args=[self.revision.pk]), {"revision": 1}, content_type=JSON).status_code, 403)
        self.assertEqual(self.client.patch(reverse("revision-edit", args=[self.revision.pk]), revision_body(revision=1), content_type=JSON).status_code, 403)

    def test_operations_assignment_is_required_and_audited(self):
        url = reverse("survey-assign", args=[self.survey.pk])
        self.assertEqual(self.client.post(url, {"assigned_to": self.other.pk, "revision": 1}, content_type=JSON).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.post(url, {"assigned_to": self.other.pk, "revision": 1}, content_type=JSON).status_code, 200)
        self.assertEqual(self.client.post(url, {"assigned_to": self.other.pk, "revision": 1}, content_type=JSON).status_code, 409)
        self.assertTrue(AuditEvent.objects.filter(record_type="surveys.survey", action="assigned", actor=self.manager).exists())

    def test_requested_revision_is_corrected_and_resubmitted_with_previous_snapshot_retained(self):
        self.revision.submit()
        self.revision.review("changes_requested", self.manager, "Measure the cable route again")
        url = reverse("revision-edit", args=[self.revision.pk])
        data = revision_body(revision=self.revision.revision, cable_distance_m="41.00",
                             surveyed_at=self.revision.surveyed_at.isoformat())
        response = self.client.patch(url, data, content_type=JSON)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(self.client.patch(url, data, content_type=JSON).status_code, 409)
        submit = self.client.post(reverse("revision-submit", args=[self.revision.pk]),
                                  {"revision": response.json()["revision"]}, content_type=JSON)
        self.assertEqual(submit.status_code, 200)
        self.assertEqual(SurveyRevision.objects.count(), 1)
        self.assertEqual(AuditEvent.objects.filter(action="submitted", record_id=self.revision.pk).count(), 2)
        correction = AuditEvent.objects.get(action="corrected")
        self.assertEqual(correction.before["cable_distance_m"], "22.50")
        self.assertEqual(correction.after["cable_distance_m"], "41.00")

    def test_actual_event_time_correction_requires_reason(self):
        data = revision_body(revision=self.revision.revision, surveyed_at=timezone.now().isoformat())
        url = reverse("revision-edit", args=[self.revision.pk])
        self.assertEqual(self.client.patch(url, data, content_type=JSON).status_code, 400)
        response = self.client.patch(url, {**data, "reason": "Corrected from the field notebook"}, content_type=JSON)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(AuditEvent.objects.filter(action="corrected", reason="Corrected from the field notebook").exists())

    def test_approved_and_submitted_measurements_stay_locked(self):
        self.revision.submit()
        data = revision_body(revision=self.revision.revision)
        self.assertEqual(self.client.patch(reverse("revision-edit", args=[self.revision.pk]), data, content_type=JSON).status_code, 400)
        self.revision.review("approved", self.manager)
        data["revision"] = self.revision.revision
        self.assertEqual(self.client.patch(reverse("revision-edit", args=[self.revision.pk]), data, content_type=JSON).status_code, 400)

    def test_finance_cannot_read_survey_or_start_capture(self):
        self.client.force_login(User.objects.create_user("finance", roles=[Role.FINANCE]))
        self.assertEqual(self.client.get(reverse("survey-list")).status_code, 403)
        self.assertEqual(self.client.post(reverse("survey-start"), {"enquiry": self.survey.enquiry_id}).status_code, 403)
