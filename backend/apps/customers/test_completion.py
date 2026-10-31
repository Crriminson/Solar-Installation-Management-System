"""F01/F02 completion: address flags, review evidence, qualification, stale writes and role boundaries."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.api import business_date
from apps.core.models import AuditEvent
from .models import Enquiry
from .tests import VALID_PAYLOAD

User = get_user_model()
JSON = "application/json"


class EnquiryCompletionTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.post(reverse("enquiry-create"), VALID_PAYLOAD)
        self.enquiry = Enquiry.objects.get()
        self.sales = User.objects.create_user("seller", roles=[Role.SALES])
        self.client.force_login(self.sales)



    def test_intake_has_a_next_action_and_due_date_without_an_owner(self):
        self.assertIsNone(self.enquiry.owner)
        self.assertTrue(self.enquiry.next_action)
        self.assertEqual(self.enquiry.next_action_due, business_date())

    def test_matching_normalized_address_flags_even_with_a_different_phone(self):
        response = self.client.post(reverse("enquiry-create"), {
            **VALID_PAYLOAD, "phone": "9000000000", "address_line": "12, NEHRU ROAD.",
        })
        self.assertEqual(response.status_code, 201)
        latest = Enquiry.objects.latest("id")
        self.assertEqual(latest.possible_duplicate_of_id, self.enquiry.site.customer_id)
        self.assertEqual(Enquiry.objects.count(), 2)

    def test_duplicate_review_requires_reason_preserves_both_records_and_is_audited(self):
        self.client.post(reverse("enquiry-create"), VALID_PAYLOAD)
        latest = Enquiry.objects.latest("id")
        url = reverse("enquiry-duplicate-review", args=[latest.pk])
        data = {"revision": latest.revision, "decision": "distinct"}
        self.assertEqual(self.client.post(url, data, content_type=JSON).status_code, 400)
        response = self.client.post(url, {**data, "reason": "Different household at the same address"}, content_type=JSON)
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["is_possible_duplicate"])
        self.assertEqual(Enquiry.objects.count(), 2)
        self.assertTrue(AuditEvent.objects.filter(action="duplicate_reviewed", actor=self.sales).exists())







    def test_page_size_is_capped_and_sort_is_stable(self):
        response = self.client.get(reverse("enquiry-list"), {"page_size": 9999, "sort": "due"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["count"], 1)

    def test_negative_usage_and_money_are_rejected(self):
        for field in ("monthly_consumption_kwh", "monthly_bill_amount", "shadow_free_roof_area_sqm"):
            response = self.client.post(reverse("enquiry-create"), {**VALID_PAYLOAD, field: "-1"})
            self.assertEqual(response.status_code, 400, field)

    def test_a_bill_amount_requires_its_billing_period(self):
        payload = {**VALID_PAYLOAD}
        payload.pop("billing_period_start")
        response = self.client.post(reverse("enquiry-create"), payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("billing_period_start", response.json())
