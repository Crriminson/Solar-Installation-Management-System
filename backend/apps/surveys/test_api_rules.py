"""
Tests for F03 rules enforced at the API.

Covers what the survey screens rely on: limits on measurements, photos
as evidence, closed enquiries, a list that stays cheap as it grows, and
two technicians filing at the same moment.
"""

import io
import shutil
import tempfile
import threading
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, connections
from django.test import Client, TestCase, TransactionTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from apps.accounts.models import Role
from apps.customers.models import Customer, Enquiry, EnquiryStatus, Site

from .models import RevisionStatus, Survey, SurveyPhoto, SurveyRevision
from .tests import VALID_SURVEY, make_revision

User = get_user_model()

JSON = "application/json"
PASSWORD = "test-pass-123"
PARALLEL_TECHNICIANS = 6


def make_enquiry(number=0):
    customer = Customer.objects.create(
        full_name=f"Customer {number}", phone=f"97000{number:05d}"
    )
    site = Site.objects.create(
        customer=customer, address_line="1 Road", city="Jaipur",
        state="Rajasthan", pincode="302001",
    )
    return Enquiry.objects.create(site=site, source="phone")


def revision_body(**overrides):
    return {
        **VALID_SURVEY,
        "surveyed_at": (timezone.now() - timedelta(hours=1)).isoformat(),
        **overrides,
    }


def make_photo(name="roof.png"):
    buffer = io.BytesIO()
    Image.new("RGB", (4, 4)).save(buffer, format="PNG")
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class SurveyApiTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.technician = User.objects.create_user(
            username="tech", password=PASSWORD, roles=[Role.TECHNICIAN]
        )
        self.manager = User.objects.create_user(
            username="mgr", password=PASSWORD, roles=[Role.OPERATIONS_MANAGER]
        )
        self.survey = Survey.objects.create(enquiry=make_enquiry(), assigned_to=self.technician)
        self.client.login(username="tech", password=PASSWORD)


class MeasurementLimitTests(SurveyApiTestCase):
    def post(self, **overrides):
        return self.client.post(
            reverse("revision-create", args=[self.survey.id]),
            revision_body(**overrides),
            content_type=JSON,
        )

    def test_impossible_measurements_are_refused_by_field(self):
        for field, value in [
            ("recommended_capacity_kw", "-3.00"),
            ("cable_distance_m", "-5.00"),
            ("cable_distance_m", "0.00"),
            ("roof_length_m", "-10.00"),
        ]:
            response = self.post(**{field: value})

            self.assertEqual(response.status_code, 400, field)
            self.assertIn(field, response.json())

    def test_a_survey_must_recommend_a_system_type(self):
        response = self.post(recommended_system_type="undecided")

        self.assertEqual(response.status_code, 400)
        self.assertIn("recommended_system_type", response.json())

    def test_a_survey_cannot_be_dated_in_the_future(self):
        future = (timezone.now() + timedelta(days=1)).isoformat()

        response = self.post(surveyed_at=future)

        self.assertEqual(response.status_code, 400)
        self.assertIn("surveyed_at", response.json())


class StartSurveyTests(SurveyApiTestCase):
    def start(self, enquiry):
        self.client.force_login(self.manager)
        return self.client.post(
            reverse("survey-start"), {"enquiry": enquiry}, content_type=JSON
        )

    def test_an_enquiry_id_that_is_not_a_number_is_refused(self):
        self.assertEqual(self.start("abc").status_code, 400)

    def test_a_lost_enquiry_cannot_start_a_survey(self):
        enquiry = make_enquiry(1)
        enquiry.change_status(EnquiryStatus.LOST, reason="Gone")

        self.assertEqual(self.start(enquiry.id).status_code, 400)

    def test_a_lost_enquiry_keeps_its_existing_survey_readable(self):
        enquiry = self.survey.enquiry
        enquiry.change_status(EnquiryStatus.LOST, reason="Gone")

        self.assertEqual(self.start(enquiry.id).status_code, 200)


class ReviewApiTests(SurveyApiTestCase):
    def test_an_approved_survey_can_take_a_new_revision(self):
        """Spec.md F03: later changes create a new revision."""
        first = make_revision(self.survey, self.technician)
        first.submit()
        first.review(RevisionStatus.APPROVED, reviewer=self.manager)

        response = self.client.post(
            reverse("revision-create", args=[self.survey.id]),
            revision_body(),
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 201)

    def test_approving_through_the_api_replaces_the_earlier_approval(self):
        first = make_revision(self.survey, self.technician)
        first.submit()
        first.review(RevisionStatus.APPROVED, reviewer=self.manager)
        second = make_revision(self.survey, self.technician)
        second.submit()
        self.client.login(username="mgr", password=PASSWORD)

        response = self.client.post(
            reverse("revision-review", args=[second.id]),
            {"decision": "approved", "revision": second.revision},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.status, RevisionStatus.SUPERSEDED)

    def test_a_technician_cannot_reject_through_the_api(self):
        revision = make_revision(self.survey, self.technician)
        revision.submit()

        response = self.client.post(
            reverse("revision-review", args=[revision.id]),
            {"decision": "rejected", "notes": "No"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 403)
        revision.refresh_from_db()
        self.assertEqual(revision.status, RevisionStatus.SUBMITTED)


class SurveyListTests(SurveyApiTestCase):
    def setUp(self):
        super().setUp()
        self.client.force_login(self.manager)

    def count(self, **params):
        return self.client.get(reverse("survey-list"), params).json()["count"]

    def test_the_pending_view_holds_only_surveys_awaiting_review(self):
        make_revision(self.survey, self.technician).submit()
        Survey.objects.create(enquiry=make_enquiry(1))

        self.assertEqual(self.count(pending="true"), 1)

    def test_the_open_view_leaves_out_approved_surveys(self):
        revision = make_revision(self.survey, self.technician)
        revision.submit()
        revision.review(RevisionStatus.APPROVED, reviewer=self.manager)
        Survey.objects.create(enquiry=make_enquiry(1))

        self.assertEqual(self.count(open="true"), 1)

    def test_search_finds_a_survey_by_enquiry_reference(self):
        reference = self.survey.enquiry.reference

        self.assertEqual(self.count(search=reference), 1)
        self.assertEqual(self.count(search="nobody"), 0)

    def test_the_query_count_does_not_grow_with_the_list(self):
        def seed(first, last):
            for number in range(first, last):
                survey = Survey.objects.create(enquiry=make_enquiry(number))
                make_revision(survey, self.technician)
                make_revision(survey, self.technician)

        seed(1, 3)
        with CaptureQueriesContext(connection) as small:
            self.client.get(reverse("survey-list"))

        seed(3, 20)
        with CaptureQueriesContext(connection) as large:
            self.client.get(reverse("survey-list"))

        self.assertEqual(len(small), len(large))


class SurveyPhotoTests(SurveyApiTestCase):
    def setUp(self):
        super().setUp()
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)

        override = override_settings(MEDIA_ROOT=media_root)
        override.enable()
        self.addCleanup(override.disable)

        self.revision = make_revision(self.survey, self.technician)
        self.url = reverse("revision-photos", args=[self.revision.id])

    def test_a_photo_can_be_added_to_a_draft(self):
        response = self.client.post(self.url, {"image": make_photo(), "caption": "South"})

        self.assertEqual(response.status_code, 201)
        self.assertEqual(self.revision.photos.get().caption, "South")

    def test_a_submitted_revision_takes_no_more_photos(self):
        """Once submitted it is evidence, and so is what it holds."""
        self.revision.submit()

        response = self.client.post(self.url, {"image": make_photo()})

        self.assertEqual(response.status_code, 400)

    def test_a_file_that_is_not_an_image_is_refused(self):
        fake = SimpleUploadedFile("roof.png", b"MZ program", content_type="image/png")

        response = self.client.post(self.url, {"image": fake})

        self.assertEqual(response.status_code, 400)
        self.assertEqual(SurveyPhoto.objects.count(), 0)

    @override_settings(MAX_PHOTOS_PER_RECORD=1)
    def test_the_photo_limit_is_enforced(self):
        self.client.post(self.url, {"image": make_photo()})

        response = self.client.post(self.url, {"image": make_photo("two.png")})

        self.assertEqual(response.status_code, 400)

    def test_a_photo_can_only_be_viewed_when_signed_in(self):
        self.client.post(self.url, {"image": make_photo()})
        file_url = self.revision.photos.get().id

        signed_in = self.client.get(reverse("survey-photo-file", args=[file_url]))
        self.client.logout()
        signed_out = self.client.get(reverse("survey-photo-file", args=[file_url]))

        self.assertEqual(signed_in.status_code, 200)
        self.assertIn(signed_out.status_code, [401, 403])


class SimultaneousApprovalTests(TransactionTestCase):
    def test_two_approvals_at_once_leave_exactly_one_approved(self):
        """The survey row lock makes one approval wait for the other."""
        technician = User.objects.create_user("tech", password=PASSWORD)
        User.objects.create_user(
            "mgr", password=PASSWORD, roles=[Role.OPERATIONS_MANAGER]
        )
        survey = Survey.objects.create(enquiry=make_enquiry())

        revisions = [make_revision(survey, technician) for _ in range(2)]
        for revision in revisions:
            revision.submit()

        barrier = threading.Barrier(len(revisions))
        codes = []

        def approve(revision):
            client = Client(raise_request_exception=False)
            client.login(username="mgr", password=PASSWORD)
            barrier.wait()
            response = client.post(
                reverse("revision-review", args=[revision.id]),
                {"decision": "approved", "revision": revision.revision},
                content_type=JSON,
            )
            codes.append(response.status_code)
            connections.close_all()

        threads = [
            threading.Thread(target=approve, args=[revision]) for revision in revisions
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(codes, [200, 200])
        statuses = sorted(survey.revisions.values_list("status", flat=True))
        self.assertEqual(statuses, [RevisionStatus.APPROVED, RevisionStatus.SUPERSEDED])


class RevisionNumberingConcurrencyTests(TransactionTestCase):
    def test_simultaneous_first_revisions_all_save_with_their_own_number(self):
        """A first revision has no rows to lock, so the survey is locked."""
        technician = User.objects.create_user("tech", password=PASSWORD, roles=[Role.TECHNICIAN])
        survey = Survey.objects.create(enquiry=make_enquiry(), assigned_to=technician)
        barrier = threading.Barrier(PARALLEL_TECHNICIANS)
        codes = []

        def file_a_revision():
            client = Client(raise_request_exception=False)
            client.login(username="tech", password=PASSWORD)
            barrier.wait()
            response = client.post(
                reverse("revision-create", args=[survey.id]),
                revision_body(),
                content_type=JSON,
            )
            codes.append(response.status_code)
            connections.close_all()

        threads = [
            threading.Thread(target=file_a_revision)
            for _ in range(PARALLEL_TECHNICIANS)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(codes, [201] * PARALLEL_TECHNICIANS)
        numbers = sorted(
            SurveyRevision.objects.values_list("revision_number", flat=True)
        )
        self.assertEqual(numbers, list(range(1, PARALLEL_TECHNICIANS + 1)))
