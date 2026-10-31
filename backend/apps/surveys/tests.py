"""
Tests for F03 — survey and approval.

The rules worth proving: a reviewed revision is frozen, only an
operations manager can approve, an off-grid survey cannot be recorded
without the figures a battery needs, and a survey can never end up with
two approved revisions for a quotation to choose between.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.customers.models import Enquiry
from apps.customers.tests import VALID_PAYLOAD

from .models import RevisionStatus, Survey, SurveyRevision

User = get_user_model()


# A complete, valid on-grid survey.
VALID_SURVEY = {
    "roof_type": "flat_rcc",
    "roof_length_m": "10.00",
    "roof_width_m": "8.00",
    "usable_area_sqm": "45.00",
    "orientation": "S",
    "tilt_degrees": "15.0",
    "cable_distance_m": "22.50",
    "recommended_system_type": "on_grid",
    "recommended_capacity_kw": "3.00",
}


def make_survey(client):
    """Creates an enquiry and opens its survey."""
    cache.clear()
    client.post(reverse("enquiry-create"), VALID_PAYLOAD)
    return Survey.objects.create(enquiry=Enquiry.objects.get())


def make_revision(survey, technician, **overrides):
    fields = {**VALID_SURVEY, **overrides}
    revision = SurveyRevision(
        survey=survey,
        surveyed_by=technician,
        surveyed_at=timezone.now() - timedelta(hours=2),
        **fields,
    )
    revision.save()
    return revision


class RevisionNumberingTests(TestCase):
    def setUp(self):
        self.survey = make_survey(self.client)
        self.technician = User.objects.create_user(
            username="tech", password="x", roles=[Role.TECHNICIAN]
        )

    def test_first_revision_is_number_one(self):
        revision = make_revision(self.survey, self.technician)

        self.assertEqual(revision.revision_number, 1)

    def test_revisions_number_upwards(self):
        make_revision(self.survey, self.technician)
        second = make_revision(self.survey, self.technician)

        self.assertEqual(second.revision_number, 2)

    def test_a_new_survey_has_no_approved_revision(self):
        self.assertFalse(self.survey.is_approved)
        self.assertIsNone(self.survey.approved_revision)


class ImmutabilityTests(TestCase):
    """A reviewed revision is evidence, not a working document."""

    def setUp(self):
        self.survey = make_survey(self.client)
        self.technician = User.objects.create_user(
            username="tech", password="x", roles=[Role.TECHNICIAN]
        )
        self.revision = make_revision(self.survey, self.technician)

    def test_a_draft_can_be_edited(self):
        self.revision.shading_notes = "Water tank on the south edge"
        self.revision.save()

        self.revision.refresh_from_db()
        self.assertEqual(self.revision.shading_notes, "Water tank on the south edge")

    def test_a_submitted_revision_cannot_be_edited(self):
        self.revision.submit()

        self.revision.cable_distance_m = "99.00"
        with self.assertRaises(ValidationError):
            self.revision.save()

    def test_an_approved_revision_cannot_be_edited(self):
        manager = User.objects.create_user(
            username="mgr", password="x", roles=[Role.OPERATIONS_MANAGER]
        )
        self.revision.submit()
        self.revision.review(RevisionStatus.APPROVED, reviewer=manager)

        self.revision.recommended_capacity_kw = "5.00"
        with self.assertRaises(ValidationError):
            self.revision.save()


class ReviewFlowTests(TestCase):
    def setUp(self):
        self.survey = make_survey(self.client)
        self.technician = User.objects.create_user(
            username="tech", password="x", roles=[Role.TECHNICIAN]
        )
        self.manager = User.objects.create_user(
            username="mgr", password="x", roles=[Role.OPERATIONS_MANAGER]
        )
        self.revision = make_revision(self.survey, self.technician)

    def test_a_draft_cannot_be_approved_without_being_submitted(self):
        with self.assertRaises(ValidationError):
            self.revision.review(RevisionStatus.APPROVED, reviewer=self.manager)

    def test_a_technician_cannot_approve_a_survey(self):
        """Approval unlocks quoting, so it is the manager's decision."""
        self.revision.submit()

        with self.assertRaises(ValidationError):
            self.revision.review(RevisionStatus.APPROVED, reviewer=self.technician)

    def test_a_manager_can_approve(self):
        self.revision.submit()
        self.revision.review(RevisionStatus.APPROVED, reviewer=self.manager)

        self.survey.refresh_from_db()
        self.assertTrue(self.survey.is_approved)
        self.assertEqual(self.survey.approved_revision, self.revision)

    def test_an_administrator_can_also_approve(self):
        admin = User.objects.create_user(
            username="admin2", password="x", roles=[Role.ADMINISTRATOR]
        )
        self.revision.submit()
        self.revision.review(RevisionStatus.APPROVED, reviewer=admin)

        self.assertTrue(self.survey.is_approved)

    def test_requesting_changes_without_saying_why_is_refused(self):
        self.revision.submit()

        with self.assertRaises(ValidationError):
            self.revision.review(
                RevisionStatus.CHANGES_REQUESTED, reviewer=self.manager, notes=""
            )

    def test_requesting_changes_records_the_reason(self):
        self.revision.submit()
        self.revision.review(
            RevisionStatus.CHANGES_REQUESTED,
            reviewer=self.manager,
            notes="Cable distance looks measured straight-line",
        )

        self.assertEqual(self.revision.status, RevisionStatus.CHANGES_REQUESTED)
        self.assertIn("straight-line", self.revision.review_notes)

    def test_a_bounced_revision_is_answered_with_a_new_one(self):
        self.revision.submit()
        self.revision.review(
            RevisionStatus.CHANGES_REQUESTED, reviewer=self.manager, notes="Remeasure"
        )

        corrected = make_revision(self.survey, self.technician, cable_distance_m="31.00")

        self.assertEqual(corrected.revision_number, 2)
        # The bounced revision is untouched.
        self.revision.refresh_from_db()
        self.assertEqual(self.revision.status, RevisionStatus.CHANGES_REQUESTED)

    def test_a_survey_cannot_have_two_approved_revisions(self):
        """A quotation must never have two sources to choose between."""
        self.revision.submit()
        self.revision.review(RevisionStatus.APPROVED, reviewer=self.manager)

        second = make_revision(self.survey, self.technician)
        second.submit()

        with self.assertRaises((IntegrityError, ValidationError)):
            with transaction.atomic():
                second.review(RevisionStatus.APPROVED, reviewer=self.manager)


class MeasurementRuleTests(TestCase):
    def setUp(self):
        self.survey = make_survey(self.client)
        self.technician = User.objects.create_user(
            username="tech", password="x", roles=[Role.TECHNICIAN]
        )

    def test_off_grid_needs_load_and_backup_duration(self):
        """Battery size cannot be inferred from panel capacity."""
        revision = SurveyRevision(
            survey=self.survey,
            surveyed_by=self.technician,
            surveyed_at=timezone.now(),
            **{**VALID_SURVEY, "recommended_system_type": "off_grid"},
        )

        with self.assertRaises(ValidationError):
            revision.clean()

    def test_off_grid_with_both_figures_is_accepted(self):
        revision = SurveyRevision(
            survey=self.survey,
            surveyed_by=self.technician,
            surveyed_at=timezone.now(),
            **{
                **VALID_SURVEY,
                "recommended_system_type": "off_grid",
                "critical_load_kw": "1.50",
                "backup_duration_hours": "6.0",
            },
        )

        revision.clean()  # must not raise

    def test_usable_area_cannot_exceed_the_measured_roof(self):
        revision = SurveyRevision(
            survey=self.survey,
            surveyed_by=self.technician,
            surveyed_at=timezone.now(),
            **{**VALID_SURVEY, "usable_area_sqm": "500.00"},
        )

        with self.assertRaises(ValidationError):
            revision.clean()


class SurveyApiTests(TestCase):
    def setUp(self):
        self.survey = make_survey(self.client)
        self.technician = User.objects.create_user(
            username="tech", password="test-pass-123", roles=[Role.TECHNICIAN]
        )
        self.manager = User.objects.create_user(
            username="mgr", password="test-pass-123", roles=[Role.OPERATIONS_MANAGER]
        )
        self.client.login(username="tech", password="test-pass-123")

    def test_creating_a_revision_records_the_logged_in_technician(self):
        response = self.client.post(
            reverse("revision-create", args=[self.survey.id]),
            {**VALID_SURVEY, "surveyed_at": timezone.now().isoformat()},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(SurveyRevision.objects.get().surveyed_by, self.technician)

    def test_off_grid_without_battery_figures_is_rejected_by_the_api(self):
        response = self.client.post(
            reverse("revision-create", args=[self.survey.id]),
            {
                **VALID_SURVEY,
                "recommended_system_type": "off_grid",
                "surveyed_at": timezone.now().isoformat(),
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_technician_approving_through_the_api_is_refused(self):
        revision = make_revision(self.survey, self.technician)
        revision.submit()

        response = self.client.post(
            reverse("revision-review", args=[revision.id]),
            {"decision": "approved"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("operations manager", response.json()["detail"])

    def test_manager_approving_through_the_api_succeeds(self):
        revision = make_revision(self.survey, self.technician)
        revision.submit()
        self.client.login(username="mgr", password="test-pass-123")

        response = self.client.post(
            reverse("revision-review", args=[revision.id]),
            {"decision": "approved"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertTrue(Survey.objects.get().is_approved)

    def test_starting_a_survey_twice_returns_the_same_one(self):
        enquiry = self.survey.enquiry

        response = self.client.post(
            reverse("survey-start"),
            {"enquiry": enquiry.id},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Survey.objects.count(), 1)

    def test_surveys_require_login(self):
        self.client.logout()

        response = self.client.get(reverse("survey-list"))

        self.assertIn(response.status_code, [401, 403])
