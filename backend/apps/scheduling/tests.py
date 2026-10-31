"""
F10 - what scheduling has to prove.

A technician cannot be in two places at once, a job that moves keeps
the slot it used to hold, and a crew is never sent to fit materials
that have not arrived.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.customers.models import Customer, Site

from .models import Job, JobKind, JobStatus, ScheduleChange

User = get_user_model()
JSON = "application/json"


def slot(hours_from_now, length_hours=2):
    start = timezone.now() + timedelta(hours=hours_from_now)
    return start, start + timedelta(hours=length_hours)


class SchedulingTestCase(TestCase):
    def setUp(self):
        self.manager = User.objects.create_user("sch_mgr", roles=[Role.OPERATIONS_MANAGER])
        self.alice = User.objects.create_user("alice", roles=[Role.TECHNICIAN])
        self.bob = User.objects.create_user("bob", roles=[Role.TECHNICIAN])
        self.sales = User.objects.create_user("sch_sales", roles=[Role.SALES])

        customer = Customer.objects.create(full_name="Ramesh Gupta", phone="9876543210")
        self.site = Site.objects.create(
            customer=customer, address_line="14 Vikas Nagar", city="Lucknow",
            state="Uttar Pradesh", pincode="226022",
        )
        self.client.force_login(self.manager)

    def book(self, technicians, hours_from_now=24, length_hours=2,
             kind=JobKind.SURVEY, **extra):
        starts_at, ends_at = slot(hours_from_now, length_hours)
        return self.client.post(reverse("job-create"), {
            "kind": kind, "site": self.site.pk,
            "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat(),
            "technicians": [person.pk for person in technicians], **extra,
        }, content_type=JSON)


class BookingTests(SchedulingTestCase):
    def test_booking_staffs_the_job_and_names_a_lead(self):
        response = self.book([self.alice, self.bob])

        self.assertEqual(response.status_code, 201, response.content)
        job = Job.objects.get()
        self.assertEqual(job.status, JobStatus.SCHEDULED)
        self.assertEqual(len(job.technicians), 2)
        self.assertTrue(job.assignments.get(technician=self.alice).is_lead)

    def test_a_technician_cannot_be_in_two_places_at_once(self):
        self.book([self.alice], hours_from_now=24)

        clash = self.book([self.alice], hours_from_now=25)

        self.assertEqual(clash.status_code, 400)
        self.assertIn("already on", str(clash.content))
        self.assertEqual(Job.objects.count(), 1)

    def test_back_to_back_jobs_are_fine(self):
        """A job ending at 11:00 and the next starting at 11:00 do not overlap."""
        self.book([self.alice], hours_from_now=24, length_hours=2)

        next_job = self.book([self.alice], hours_from_now=26, length_hours=2)

        self.assertEqual(next_job.status_code, 201, next_job.content)
        self.assertEqual(Job.objects.count(), 2)

    def test_another_technician_can_take_the_same_slot(self):
        self.book([self.alice], hours_from_now=24)

        response = self.book([self.bob], hours_from_now=24)

        self.assertEqual(response.status_code, 201, response.content)

    def test_a_job_cannot_end_before_it_starts(self):
        starts_at, _ = slot(24)
        response = self.client.post(reverse("job-create"), {
            "kind": JobKind.SURVEY, "site": self.site.pk,
            "starts_at": starts_at.isoformat(),
            "ends_at": (starts_at - timedelta(hours=1)).isoformat(),
            "technicians": [self.alice.pk],
        }, content_type=JSON)

        self.assertEqual(response.status_code, 400)

    def test_somebody_who_is_not_a_technician_cannot_be_sent(self):
        response = self.book([self.sales])

        self.assertEqual(response.status_code, 400)
        self.assertIn("not a technician", str(response.content))


class RescheduleTests(SchedulingTestCase):
    def setUp(self):
        super().setUp()
        self.book([self.alice])
        self.job = Job.objects.get()

    def move_to(self, hours_from_now, reason="Customer asked for the afternoon"):
        starts_at, ends_at = slot(hours_from_now)
        self.job.refresh_from_db()
        return self.client.post(
            reverse("job-action", args=[self.job.pk, "reschedule"]),
            {"revision": self.job.revision, "reason": reason,
             "starts_at": starts_at.isoformat(), "ends_at": ends_at.isoformat()},
            content_type=JSON,
        )

    def test_moving_a_job_keeps_the_slot_it_used_to_hold(self):
        original_start = self.job.starts_at

        response = self.move_to(48)

        self.assertEqual(response.status_code, 200, response.content)
        change = ScheduleChange.objects.get()
        self.assertEqual(change.previous_starts_at, original_start)
        self.assertIn("afternoon", change.reason)

    def test_moving_a_job_without_a_reason_is_refused(self):
        response = self.move_to(48, reason="")

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ScheduleChange.objects.exists())

    def test_a_job_cannot_move_onto_a_slot_the_crew_already_holds(self):
        self.book([self.alice], hours_from_now=72)

        response = self.move_to(72)

        self.assertEqual(response.status_code, 400)
        self.assertIn("already booked", str(response.content))


class BlockingTests(SchedulingTestCase):
    def setUp(self):
        super().setUp()
        self.book([self.alice])
        self.job = Job.objects.get()

    def test_a_delay_is_recorded_against_somebody(self):
        response = self.client.post(
            reverse("job-action", args=[self.job.pk, "block"]),
            {"revision": self.job.revision, "reason": "Scaffolding not up",
             "owner": self.manager.pk},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.job.refresh_from_db()
        self.assertTrue(self.job.is_blocked)
        self.assertEqual(self.job.blocked_owner, self.manager)

    def test_a_delay_with_nobody_to_clear_it_is_refused(self):
        response = self.client.post(
            reverse("job-action", args=[self.job.pk, "block"]),
            {"revision": self.job.revision, "reason": "Scaffolding not up"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 400)


class TechnicianViewTests(SchedulingTestCase):
    def setUp(self):
        super().setUp()
        self.book([self.alice])
        self.book([self.bob], hours_from_now=48)

    def test_a_technician_sees_only_their_own_jobs(self):
        self.client.force_login(self.alice)

        response = self.client.get(reverse("job-list"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_a_technician_is_not_shown_the_commercial_detail(self):
        """Spec.md F10: the detail the job requires, and no more."""
        self.client.force_login(self.alice)

        row = self.client.get(reverse("job-list")).json()["results"][0]

        self.assertIn("site_address", row)
        self.assertNotIn("order_reference", row)
        self.assertNotIn("schedule_changes", row)
        self.assertNotIn("blocked_owner", row)

    def test_the_office_sees_the_whole_diary(self):
        response = self.client.get(reverse("job-list"))

        self.assertEqual(response.json()["count"], 2)

    def test_a_technician_cannot_book_work(self):
        self.client.force_login(self.alice)

        response = self.book([self.alice], hours_from_now=96)

        self.assertEqual(response.status_code, 403)


class InstallationGateTests(SchedulingTestCase):
    def test_an_installation_cannot_start_without_an_order(self):
        self.book([self.alice], kind=JobKind.INSTALLATION)
        job = Job.objects.get()

        response = self.client.post(
            reverse("job-action", args=[job.pk, "start"]),
            {"revision": job.revision}, content_type=JSON,
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("order", str(response.content).lower())

    def test_a_survey_starts_without_any_materials(self):
        self.book([self.alice], kind=JobKind.SURVEY)
        job = Job.objects.get()

        response = self.client.post(
            reverse("job-action", args=[job.pk, "start"]),
            {"revision": job.revision}, content_type=JSON,
        )

        self.assertEqual(response.status_code, 200, response.content)
        job.refresh_from_db()
        self.assertEqual(job.status, JobStatus.IN_PROGRESS)
