"""F01/F02 completion: address flags, review evidence, qualification, stale writes and role boundaries."""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.api import business_date
from apps.core.models import AuditEvent
from .models import Enquiry, QUALIFICATION_CHECKS
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

    def assign(self, **changes):
        return self.client.patch(reverse("enquiry-assign", args=[self.enquiry.pk]), {
            "revision": self.enquiry.revision, "owner": self.sales.pk,
            "next_action": "Call customer", "next_action_due": str(business_date()), **changes,
        }, content_type=JSON)

    def move(self, target, **changes):
        self.enquiry.refresh_from_db()
        return self.client.post(reverse("enquiry-status", args=[self.enquiry.pk]), {
            "revision": self.enquiry.revision, "status": target, "next_action": "Book visit",
            "next_action_due": str(business_date()), **changes,
        }, content_type=JSON)

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

    def test_owner_due_and_revision_are_required_on_assignment(self):
        self.assertEqual(self.assign(next_action_due=None).status_code, 400)
        self.assertEqual(self.assign(revision=99).status_code, 409)
        self.assertEqual(self.assign().status_code, 200)
        self.assertEqual(self.assign().status_code, 409)

    def test_a_non_sales_owner_is_refused(self):
        technician = User.objects.create_user("technician", roles=[Role.TECHNICIAN])
        self.assertEqual(self.assign(owner=technician.pk).status_code, 400)

    def test_qualification_requires_all_checks_and_a_reason(self):
        self.assertEqual(self.assign().status_code, 200)
        self.assertEqual(self.move("contacting").status_code, 200)
        self.assertEqual(self.move("qualified").status_code, 400)
        checks = {name: True for name in QUALIFICATION_CHECKS}
        self.assertEqual(self.move("qualified", qualification_checks=checks).status_code, 400)
        checks["grid"] = False
        self.assertEqual(self.move("qualified", qualification_checks=checks, reason="Reviewed").status_code, 400)
        checks["grid"] = True
        response = self.move("qualified", qualification_checks=checks, reason="Roof, usage, grid, requirements and documents confirmed")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["qualification_checks"], checks)
        self.assertTrue(AuditEvent.objects.filter(action="status_changed", after__status="qualified").exists())

    def test_contacting_without_owner_or_due_is_refused(self):
        self.assertEqual(self.move("contacting").status_code, 400)
        self.assign()
        self.assertEqual(self.move("contacting", next_action_due=None).status_code, 400)

    def test_contacts_for_unknown_enquiry_return_404_instead_of_a_server_error(self):
        response = self.client.post(reverse("enquiry-contacts", args=[999999]), {
            "channel": "phone", "summary": "Called", "contacted_at": "2026-10-30T10:00:00Z",
        }, content_type=JSON)
        self.assertEqual(response.status_code, 404)

    def test_enquiry_roles_for_reads_actions_contacts_review_and_activity(self):
        for role in Role.values:
            user = User.objects.create_user(f"reader-{role}", roles=[role])
            self.client.force_login(user)
            readable = role in (Role.SALES, Role.OPERATIONS_MANAGER, Role.DIRECTOR, Role.ADMINISTRATOR)
            writable = role in (Role.SALES, Role.OPERATIONS_MANAGER, Role.ADMINISTRATOR)
            for name in ("enquiry-list", "enquiry-contacts", "enquiry-activity"):
                url = reverse(name) if name == "enquiry-list" else reverse(name, args=[self.enquiry.pk])
                self.assertEqual(self.client.get(url).status_code, 200 if readable else 403, (role, name))
            if not writable:
                self.assertEqual(self.assign().status_code, 403, role)
                self.assertEqual(self.move("lost", reason="No interest").status_code, 403, role)
                self.assertEqual(self.client.post(reverse("enquiry-duplicate-review", args=[self.enquiry.pk]), {}).status_code, 403)

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
