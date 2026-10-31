"""
Tests for F02 — qualification and follow-up.

The rules worth proving: an enquiry cannot skip stages, a lost lead
always carries a reason, nothing is left with no next action, and a
closed lead stops appearing as work.
"""

from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.core.cache import cache
from django.urls import reverse
from django.utils import timezone

from .models import ContactLog, Enquiry, EnquiryStatus
from .tests import VALID_PAYLOAD

User = get_user_model()


def make_enquiry(client):
    """Creates one enquiry through the public endpoint."""
    client.post(reverse("enquiry-create"), VALID_PAYLOAD)
    return Enquiry.objects.get()


class StatusTransitionTests(TestCase):
    """An enquiry may only move along the allowed path."""

    def setUp(self):
        # The public endpoint is rate limited and DRF keeps its
        # counters in the cache, which outlives a single test.
        cache.clear()
        self.enquiry = make_enquiry(self.client)

    def test_new_enquiry_starts_unowned_and_open(self):
        self.assertEqual(self.enquiry.status, EnquiryStatus.NEW)
        self.assertIsNone(self.enquiry.owner)
        self.assertTrue(self.enquiry.is_open)

    def test_new_can_move_to_contacting(self):
        self.enquiry.change_status(
            EnquiryStatus.CONTACTING, next_action="Call about roof size"
        )

        self.assertEqual(self.enquiry.status, EnquiryStatus.CONTACTING)

    def test_cannot_skip_from_new_straight_to_survey_scheduled(self):
        """Nobody has spoken to this customer yet."""
        with self.assertRaises(ValidationError):
            self.enquiry.change_status(
                EnquiryStatus.SURVEY_SCHEDULED, next_action="Book survey"
            )

    def test_moving_on_without_a_next_action_is_refused(self):
        """A lead with nobody due to do anything is how leads go quiet."""
        with self.assertRaises(ValidationError):
            self.enquiry.change_status(EnquiryStatus.CONTACTING, next_action="   ")

    def test_lost_requires_a_reason(self):
        with self.assertRaises(ValidationError):
            self.enquiry.change_status(EnquiryStatus.LOST, reason="")

    def test_lost_records_the_reason_and_closes(self):
        self.enquiry.change_status(EnquiryStatus.LOST, reason="Chose another vendor")

        self.assertEqual(self.enquiry.status, EnquiryStatus.LOST)
        self.assertEqual(self.enquiry.lost_reason, "Chose another vendor")
        self.assertIsNotNone(self.enquiry.closed_at)
        self.assertFalse(self.enquiry.is_open)

    def test_lost_clears_the_pending_next_action(self):
        self.enquiry.change_status(EnquiryStatus.CONTACTING, next_action="Call back")
        self.enquiry.change_status(EnquiryStatus.LOST, reason="No budget")

        self.assertEqual(self.enquiry.next_action, "")
        self.assertIsNone(self.enquiry.next_action_due)

    def test_a_lost_enquiry_cannot_be_reopened_by_a_status_change(self):
        self.enquiry.change_status(EnquiryStatus.LOST, reason="Not interested")

        with self.assertRaises(ValidationError):
            self.enquiry.change_status(
                EnquiryStatus.CONTACTING, next_action="Try again"
            )

    def test_full_path_to_survey_scheduled(self):
        self.enquiry.change_status(EnquiryStatus.CONTACTING, next_action="Call")
        self.enquiry.change_status(EnquiryStatus.QUALIFIED, next_action="Book survey")
        self.enquiry.change_status(
            EnquiryStatus.SURVEY_SCHEDULED, next_action="Technician visits Friday"
        )

        self.assertEqual(self.enquiry.status, EnquiryStatus.SURVEY_SCHEDULED)


class OverdueTests(TestCase):
    """Overdue means an open lead whose planned action has passed."""

    def setUp(self):
        # The public endpoint is rate limited and DRF keeps its
        # counters in the cache, which outlives a single test.
        cache.clear()
        self.enquiry = make_enquiry(self.client)

    def test_lead_with_no_due_date_is_not_overdue(self):
        self.assertFalse(self.enquiry.is_overdue)

    def test_lead_past_its_due_date_is_overdue(self):
        self.enquiry.change_status(
            EnquiryStatus.CONTACTING,
            next_action="Call",
            next_action_due=timezone.localdate() - timedelta(days=1),
        )

        self.assertTrue(self.enquiry.is_overdue)

    def test_lead_due_today_is_not_yet_overdue(self):
        self.enquiry.change_status(
            EnquiryStatus.CONTACTING,
            next_action="Call",
            next_action_due=timezone.localdate(),
        )

        self.assertFalse(self.enquiry.is_overdue)

    def test_a_closed_lead_is_never_overdue(self):
        """Chasing a lost lead is noise, not work."""
        self.enquiry.change_status(
            EnquiryStatus.CONTACTING,
            next_action="Call",
            next_action_due=timezone.localdate() - timedelta(days=5),
        )
        self.enquiry.change_status(EnquiryStatus.LOST, reason="Gone cold")

        self.assertFalse(self.enquiry.is_overdue)


class FollowUpApiTests(TestCase):
    """The endpoints sales actually use."""

    def setUp(self):
        # The public endpoint is rate limited and DRF keeps its
        # counters in the cache, which outlives a single test.
        cache.clear()
        self.enquiry = make_enquiry(self.client)
        self.user = User.objects.create_user(
            username="sales", password="test-pass-123", first_name="Priya"
        )
        self.client.login(username="sales", password="test-pass-123")

    def test_assign_sets_owner_and_next_action(self):
        response = self.client.patch(
            reverse("enquiry-assign", args=[self.enquiry.id]),
            {"owner": self.user.id, "next_action": "Call about roof"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.owner, self.user)
        self.assertEqual(self.enquiry.next_action, "Call about roof")

    def test_assigning_an_unknown_staff_id_is_rejected(self):
        response = self.client.patch(
            reverse("enquiry-assign", args=[self.enquiry.id]),
            {"owner": 99999, "next_action": "Call"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_illegal_status_jump_returns_400_with_an_explanation(self):
        response = self.client.post(
            reverse("enquiry-status", args=[self.enquiry.id]),
            {"status": "survey_scheduled", "next_action": "Book"},
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Cannot move", response.json()["detail"])

    def test_recording_a_contact_stores_the_logged_in_staff_member(self):
        response = self.client.post(
            reverse("enquiry-contacts", args=[self.enquiry.id]),
            {
                "channel": "phone",
                "contacted_at": timezone.now().isoformat(),
                "summary": "Discussed roof area",
                "reached_customer": True,
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(ContactLog.objects.get().staff, self.user)

    def test_an_unanswered_call_is_still_recorded(self):
        """Knowing someone tried three times is the point of a history."""
        self.client.post(
            reverse("enquiry-contacts", args=[self.enquiry.id]),
            {
                "channel": "phone",
                "contacted_at": timezone.now().isoformat(),
                "summary": "No answer, will retry",
                "reached_customer": False,
            },
            content_type="application/json",
        )

        self.assertEqual(ContactLog.objects.count(), 1)
        self.assertFalse(ContactLog.objects.get().reached_customer)

    def test_a_contact_cannot_be_dated_in_the_future(self):
        response = self.client.post(
            reverse("enquiry-contacts", args=[self.enquiry.id]),
            {
                "channel": "phone",
                "contacted_at": (timezone.now() + timedelta(days=1)).isoformat(),
                "summary": "Time travel",
            },
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_unassigned_filter_shows_only_leads_with_no_owner(self):
        response = self.client.get(reverse("enquiry-list"), {"unassigned": "true"})
        self.assertEqual(response.json()["count"], 1)

        self.client.patch(
            reverse("enquiry-assign", args=[self.enquiry.id]),
            {"owner": self.user.id, "next_action": "Call"},
            content_type="application/json",
        )

        response = self.client.get(reverse("enquiry-list"), {"unassigned": "true"})
        self.assertEqual(response.json()["count"], 0)

    def test_overdue_filter_shows_leads_past_their_due_date(self):
        self.enquiry.change_status(
            EnquiryStatus.CONTACTING,
            next_action="Call",
            next_action_due=timezone.localdate() - timedelta(days=2),
        )

        response = self.client.get(reverse("enquiry-list"), {"overdue": "true"})

        self.assertEqual(response.json()["count"], 1)

    def test_contact_history_requires_login(self):
        self.client.logout()

        response = self.client.get(reverse("enquiry-contacts", args=[self.enquiry.id]))

        self.assertIn(response.status_code, [401, 403])
