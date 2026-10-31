"""
Tests for F01 — customers, sites and enquiries.

Covers the rules that matter, not just the happy path:
an enquiry is never lost, a duplicate phone is flagged but not blocked,
bill amount and consumption stay independent, and the sales queue is
not readable without logging in.
"""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.core.cache import cache
from django.urls import reverse

from apps.accounts.models import Role

from .models import Customer, Enquiry, Site

User = get_user_model()


# A complete, valid form submission. Individual tests copy and tweak it.
VALID_PAYLOAD = {
    "full_name": "Asha Mehta",
    "phone": "9876543210",
    "email": "asha@example.com",
    "customer_type": "residential",
    "address_line": "12 Nehru Road",
    "city": "Jaipur",
    "state": "Rajasthan",
    "pincode": "302001",
    "requested_system_type": "on_grid",
    "requested_capacity_kw": "3.00",
    "monthly_bill_amount": "2400.00",
    "billing_period_start": "2026-09-01",
    "billing_period_end": "2026-09-30",
}


class EnquirySubmissionTests(TestCase):
    """The public form at POST /api/v1/enquiries/submit/."""

    def setUp(self):
        # The public endpoint is rate limited and DRF keeps its
        # counters in the cache, which outlives a single test.
        cache.clear()
        self.url = reverse("enquiry-create")

    def test_submission_creates_all_three_records(self):
        response = self.client.post(self.url, VALID_PAYLOAD)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Customer.objects.count(), 1)
        self.assertEqual(Site.objects.count(), 1)
        self.assertEqual(Enquiry.objects.count(), 1)

    def test_response_returns_a_reference_the_customer_can_quote(self):
        response = self.client.post(self.url, VALID_PAYLOAD)

        reference = response.json()["reference"]
        self.assertTrue(reference.startswith("ENQ-"))
        self.assertTrue(Enquiry.objects.filter(reference=reference).exists())

    def test_anonymous_visitor_can_submit(self):
        """The form is public. No login, no session."""
        response = self.client.post(self.url, VALID_PAYLOAD)

        self.assertEqual(response.status_code, 201)

    def test_enquiry_is_saved_without_any_electricity_details(self):
        """
        A caller often has no bill to hand. Capturing the enquiry
        matters more than capturing the number.
        """
        payload = VALID_PAYLOAD.copy()
        payload.pop("monthly_bill_amount")

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 201)
        enquiry = Enquiry.objects.get()
        self.assertIsNone(enquiry.monthly_bill_amount)
        self.assertIsNone(enquiry.monthly_consumption_kwh)

    def test_bill_amount_does_not_populate_consumption(self):
        """
        A rupee amount is not a unit count. Slabbed tariffs mean one
        can never be derived from the other.
        """
        payload = VALID_PAYLOAD.copy()
        payload["monthly_bill_amount"] = "2400.00"

        self.client.post(self.url, payload)

        enquiry = Enquiry.objects.get()
        self.assertIsNone(enquiry.monthly_consumption_kwh)

    def test_missing_required_field_is_rejected_by_field_name(self):
        payload = VALID_PAYLOAD.copy()
        payload.pop("phone")

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json())

    def test_short_phone_number_is_rejected(self):
        payload = VALID_PAYLOAD.copy()
        payload["phone"] = "12345"

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 400)
        self.assertIn("phone", response.json())

    def test_nothing_is_saved_when_the_payload_is_invalid(self):
        """A rejected submission must not leave a half-written customer."""
        payload = VALID_PAYLOAD.copy()
        payload.pop("address_line")

        self.client.post(self.url, payload)

        self.assertEqual(Customer.objects.count(), 0)
        self.assertEqual(Site.objects.count(), 0)
        self.assertEqual(Enquiry.objects.count(), 0)

    def test_billing_period_ending_before_it_starts_is_rejected(self):
        payload = VALID_PAYLOAD.copy()
        payload["billing_period_start"] = "2026-03-01"
        payload["billing_period_end"] = "2026-02-01"

        response = self.client.post(self.url, payload)

        self.assertEqual(response.status_code, 400)


class DuplicatePhoneTests(TestCase):
    """A repeat phone number is a flag for a human, never a rejection."""

    def setUp(self):
        # The public endpoint is rate limited and DRF keeps its
        # counters in the cache, which outlives a single test.
        cache.clear()
        self.url = reverse("enquiry-create")

    def test_second_enquiry_on_same_phone_is_still_saved(self):
        self.client.post(self.url, VALID_PAYLOAD)
        response = self.client.post(self.url, VALID_PAYLOAD)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(Enquiry.objects.count(), 2)

    def test_second_enquiry_is_flagged_against_the_first_customer(self):
        self.client.post(self.url, VALID_PAYLOAD)
        first_customer = Customer.objects.get()

        self.client.post(self.url, VALID_PAYLOAD)

        latest = Enquiry.objects.order_by("-id").first()
        self.assertEqual(latest.possible_duplicate_of, first_customer)

    def test_first_enquiry_is_not_flagged(self):
        self.client.post(self.url, VALID_PAYLOAD)

        self.assertIsNone(Enquiry.objects.get().possible_duplicate_of)

    def test_phone_is_stored_as_digits_so_formats_still_match(self):
        self.client.post(self.url, VALID_PAYLOAD)

        formatted = VALID_PAYLOAD.copy()
        formatted["phone"] = "+91 98765 43210"
        self.client.post(self.url, formatted)

        # Both normalise to the same digits, so the second is flagged.
        self.assertIsNotNone(Enquiry.objects.order_by("-id").first().possible_duplicate_of)


class SalesQueuePermissionTests(TestCase):
    """GET /api/v1/enquiries/ holds customer contact details."""

    def setUp(self):
        # The public endpoint is rate limited and DRF keeps its
        # counters in the cache, which outlives a single test.
        cache.clear()
        self.url = reverse("enquiry-list")
        self.client.post(reverse("enquiry-create"), VALID_PAYLOAD)

    def test_anonymous_visitor_cannot_read_the_queue(self):
        response = self.client.get(self.url)

        self.assertIn(response.status_code, [401, 403])

    def test_logged_in_staff_can_read_the_queue(self):
        User.objects.create_user(username="sales1", password="test-pass-123", roles=["sales"])
        self.client.login(username="sales1", password="test-pass-123", roles=["sales"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_queue_can_be_searched_by_phone(self):
        User.objects.create_user(username="sales2", password="test-pass-123", roles=["sales"])
        self.client.login(username="sales2", password="test-pass-123", roles=["sales"])

        response = self.client.get(self.url, {"search": "9876543210"})

        self.assertEqual(response.json()["count"], 1)

    def test_search_with_no_match_returns_empty_not_error(self):
        User.objects.create_user(username="sales3", password="test-pass-123", roles=["sales"])
        self.client.login(username="sales3", password="test-pass-123", roles=["sales"])

        response = self.client.get(self.url, {"search": "nobody"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 0)


class SitePickerTests(TestCase):
    """F10 books crews onto sites, so the picker has to actually answer."""

    def setUp(self):
        cache.clear()
        self.staff = User.objects.create_user("picker_staff", roles=[Role.OPERATIONS_MANAGER])
        customer = Customer.objects.create(full_name="Ramesh Gupta", phone="9876543210")
        Site.objects.create(customer=customer, address_line="14 Vikas Nagar",
                            city="Lucknow", state="Uttar Pradesh", pincode="226022")

    def test_the_picker_lists_sites_with_their_customer(self):
        self.client.force_login(self.staff)

        response = self.client.get(reverse("site-list"))

        self.assertEqual(response.status_code, 200, response.content)
        row = response.json()[0]
        self.assertEqual(row["customer_name"], "Ramesh Gupta")
        self.assertEqual(row["city"], "Lucknow")

    def test_the_picker_needs_a_signed_in_staff_member(self):
        response = self.client.get(reverse("site-list"))

        self.assertIn(response.status_code, [401, 403])
