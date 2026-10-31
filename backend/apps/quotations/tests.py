"""Prove generated prices, review gates, immutable history, permissions, expiry and concurrent retries."""

import threading
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import connections
from django.test import Client, TestCase, TransactionTestCase
from django.urls import reverse

from apps.accounts.models import Role
from apps.catalogue.models import Product, ProductPrice, SizingDefaults
from apps.catalogue.tests import make_complete_on_grid
from apps.core.api import business_date
from apps.core.models import AuditEvent
from apps.customers.models import Customer, Enquiry, Site
from apps.subsidies.models import SchemeVersion
from apps.surveys.models import Survey
from apps.surveys.tests import make_revision
from .models import QuotationSettings, Quote, QuoteRequest, QuoteRevision
from .services import content_hash, document_content, expire_quotes

User = get_user_model()
JSON = "application/json"


def seed_quote_context():
    admin = User.objects.create_user("quote_admin", roles=[Role.ADMINISTRATOR])
    sales = User.objects.create_user("quote_sales", roles=[Role.SALES])
    technician = User.objects.create_user("quote_tech", roles=[Role.TECHNICIAN])
    SizingDefaults.objects.get_or_create(cable_waste_factor="1.15", cable_termination_buffer_m="5")
    QuotationSettings.objects.get_or_create(pk=1, defaults={"validity_days": 30, "advance_default_percent": "30", "advance_min_percent": "20", "advance_max_percent": "100"})
    customer = Customer.objects.create(full_name="Quote Customer", phone="9876543210")
    site = Site.objects.create(customer=customer, address_line="12 Road", city="Mumbai", state="Maharashtra", pincode="400001")
    enquiry = Enquiry.objects.create(site=site, source="phone")
    survey = Survey.objects.create(enquiry=enquiry, assigned_to=technician)
    revision = make_revision(survey, technician)
    revision.submit()
    revision.review("approved", admin)
    package = make_complete_on_grid(admin)
    package.activate(admin)
    return admin, sales, technician, enquiry, revision, package


class QuotationTests(TestCase):
    def setUp(self):
        self.admin, self.sales, self.technician, self.enquiry, self.survey, self.package = seed_quote_context()
        self.client.force_login(self.sales)

    def generate(self, key="generation", **changes):
        return self.client.post(reverse("quotation-generate"), {"enquiry": self.enquiry.pk,
                                "idempotency_key": key, **changes}, content_type=JSON)

    def action(self, quotation, action="issue", key="issue", **changes):
        return self.client.post(reverse("quotation-action", args=[quotation["id"], action]),
                                {"revision": quotation["revision"], "idempotency_key": key, **changes}, content_type=JSON)

    def generated(self):
        response = self.generate()
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def test_generation_prices_every_component_and_sums_line_gst(self):
        quote = self.generated()
        self.assertEqual(len(quote["lines"]), 8)
        cable = next(line for line in quote["lines"] if line["sku"] == "CABLE")
        self.assertEqual(cable["quantity"], "31.00")
        self.assertEqual(quote["subtotal_excl_tax"], "5300.00")
        self.assertEqual(quote["tax_amount"], "636.00")
        self.assertEqual(quote["gross_payable_incl_tax"], "5936.00")
        self.assertEqual(quote["terms"]["advance_amount_incl_tax"], "1780.80")
        self.assertEqual(quote["terms"]["balance_due"], "delivery_completion")
        self.assertNotIn("purchase_cost", str(quote))

    def test_subsidy_does_not_reduce_payable(self):
        quote = self.generated()
        self.assertEqual(quote["subsidy"][0]["amount"], "78000.00")
        self.assertFalse(quote["terms"]["subsidy_deducted"])
        self.assertEqual(quote["gross_payable_incl_tax"], "5936.00")

    def test_noneligible_commercial_has_no_subsidy_placeholder(self):
        customer = self.enquiry.site.customer
        customer.customer_type = "commercial"
        customer.save()
        self.assertEqual(self.generated()["subsidy"], [])

    def test_unknown_conditional_eligibility_blocks_partial_subsidy(self):
        site = self.enquiry.site
        site.state = "Rajasthan"
        site.save()
        response = self.generate()
        self.assertEqual(response.status_code, 400)
        self.assertIn("subsidy_facts", response.json())
        self.assertEqual(QuoteRevision.objects.count(), 0)
        response = self.generate(subsidy_facts={"rajasthan_beneficiary": False})
        self.assertEqual(response.status_code, 201)
        self.assertEqual(len(response.json()["subsidy"]), 1)

    def test_repeating_generation_returns_one_document(self):
        first = self.generated()
        second = self.generate()
        self.assertEqual(first["id"], second.json()["id"])
        self.assertEqual(Quote.objects.count(), 1)
        self.assertEqual(QuoteRevision.objects.count(), 1)

    def test_retry_key_cannot_be_reused_with_other_inputs(self):
        self.generated()
        self.assertEqual(self.generate(payment_plan="full").status_code, 409)

    def test_survey_must_be_approved(self):
        type(self.survey).objects.filter(pk=self.survey.pk).update(status="submitted")
        response = self.generate()
        self.assertEqual(response.status_code, 400)
        self.assertIn("survey", response.json())
        self.assertEqual(Quote.objects.count(), 0)

    def test_unreviewed_package_blocks_generation(self):
        type(self.package).objects.filter(pk=self.package.pk).update(status="draft", reviewed_at=None)
        self.assertEqual(self.generate().status_code, 400)
        self.assertEqual(QuoteRevision.objects.count(), 0)

    def test_missing_price_never_produces_partial_quote(self):
        ProductPrice.objects.filter(product__sku="CABLE").update(effective_from=business_date() + timedelta(days=1))
        response = self.generate()
        self.assertEqual(response.status_code, 400)
        self.assertIn("CABLE", str(response.json()))
        self.assertEqual(QuoteRevision.objects.count(), 0)

    def test_incompatible_capacity_is_named(self):
        type(self.survey).objects.filter(pk=self.survey.pk).update(recommended_capacity_kw="5")
        self.assertIn("package", self.generate().json())

    def test_advance_range_and_full_plan(self):
        self.assertEqual(self.generate(advance_percent="19.99").status_code, 400)
        quote = self.generate(payment_plan="full").json()
        self.assertEqual(quote["terms"]["balance_amount_incl_tax"], "0.00")

    def test_issue_freezes_hash_dates_and_history(self):
        draft = self.generated()
        response = self.action(draft)
        self.assertEqual(response.status_code, 200, response.content)
        issued = QuoteRevision.objects.get(pk=draft["id"])
        self.assertEqual(issued.valid_until, business_date() + timedelta(days=30))
        self.assertEqual(issued.content_hash, content_hash(document_content(issued)))
        self.assertTrue(AuditEvent.objects.filter(action="issued", actor=self.sales).exists())
        with self.assertRaises(ValidationError):
            issued.save()
        with self.assertRaises(ValidationError):
            issued.delete()

    def test_catalogue_and_address_changes_do_not_rewrite_document(self):
        draft = self.generated()
        issued = self.action(draft).json()
        Product.objects.filter(sku="PANEL").update(name="Changed name", gst_rate_percent="99")
        Site.objects.filter(pk=self.enquiry.site_id).update(address_line="Changed address")
        fetched = self.client.get(reverse("quotation-detail", args=[draft["id"]])).json()
        self.assertEqual(fetched["snapshot"], issued["snapshot"])
        self.assertEqual(fetched["lines"], issued["lines"])
        self.assertEqual(fetched["content_hash"], issued["content_hash"])

    def test_issue_retry_is_audited_once(self):
        draft = self.generated()
        self.assertEqual(self.action(draft).status_code, 200)
        self.assertEqual(self.action(draft).status_code, 200)
        self.assertEqual(AuditEvent.objects.filter(action="issued").count(), 1)

    def test_stale_action_is_rejected(self):
        draft = self.generated()
        self.assertEqual(self.action(draft, revision=0).status_code, 400)
        self.assertEqual(self.action(draft, revision=99).status_code, 409)

    def test_reissue_supersedes_and_preserves_old_revision(self):
        first = self.action(self.generated()).json()
        second = self.generate(key="second", previous_revision=first["id"], revision=first["revision"]).json()
        self.assertEqual(second["revision_number"], 2)
        self.assertEqual(self.action(second, key="issue-second").status_code, 200)
        old = QuoteRevision.objects.get(pk=first["id"])
        self.assertEqual(old.status, "superseded")
        self.assertEqual(old.content_hash, first["content_hash"])

    def test_draft_regeneration_keeps_number_and_rejects_stale_editor(self):
        draft = self.generated()
        response = self.generate(key="regenerate", previous_revision=draft["id"], revision=draft["revision"], payment_plan="full")
        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(response.json()["id"], draft["id"])
        self.assertEqual(self.action(draft).status_code, 409)
        self.assertEqual(QuoteRevision.objects.count(), 1)

    def test_revised_survey_blocks_issue_without_rewriting_snapshot(self):
        draft = self.generated()
        next_survey = make_revision(self.survey.survey, self.technician, cable_distance_m="40")
        next_survey.submit()
        next_survey.review("approved", self.admin)
        response = self.action(draft)
        self.assertEqual(response.status_code, 400)
        self.assertIn("survey", response.json())
        detail = self.client.get(reverse("quotation-detail", args=[draft["id"]])).json()
        self.assertTrue(detail["requires_survey_review"])

    def test_rejection_requires_reason_and_current_issued_state(self):
        draft = self.generated()
        self.assertEqual(self.action(draft, action="reject").status_code, 400)
        issued = self.action(draft).json()
        self.assertEqual(self.action(issued, action="reject", key="reject").status_code, 400)
        self.assertEqual(self.action(issued, action="reject", key="reject", reason="Budget changed").status_code, 200)

    def test_expiry_is_once_and_filters_match_display(self):
        issued = self.action(self.generated()).json()
        QuoteRevision.objects.filter(pk=issued["id"]).update(valid_until=business_date() - timedelta(days=1))
        response = self.client.get(reverse("quotation-list"), {"status": "expired"}).json()
        self.assertEqual(response["count"], 1)
        self.assertEqual(response["results"][0]["display_status"], "expired")
        self.assertEqual(expire_quotes(), 1)
        self.assertEqual(expire_quotes(), 0)

    def test_roles_are_enforced_for_list_detail_generation_and_actions(self):
        draft = self.generated()
        for role in Role.values:
            user = User.objects.create_user(f"role-{role}", roles=[role])
            self.client.force_login(user)
            expected_read = 200 if role in (Role.ADMINISTRATOR, Role.SALES, Role.OPERATIONS_MANAGER, Role.DIRECTOR) else 403
            self.assertEqual(self.client.get(reverse("quotation-list")).status_code, expected_read, role)
            self.assertEqual(self.client.get(reverse("quotation-detail", args=[draft["id"]])).status_code, expected_read, role)
            self.assertEqual(self.client.get(reverse("quotation-activity", args=[draft["id"]])).status_code, expected_read, role)
            if role not in (Role.ADMINISTRATOR, Role.SALES):
                self.assertEqual(self.generate().status_code, 403, role)
                self.assertEqual(self.action(draft).status_code, 403, role)
        self.client.logout()
        self.assertEqual(self.generate().status_code, 403)


class QuotationConcurrencyTests(TransactionTestCase):
    def setUp(self):
        self.admin, self.sales, self.tech, self.enquiry, self.survey, self.package = seed_quote_context()

    def test_simultaneous_generation_with_same_key_creates_one_revision(self):
        barrier = threading.Barrier(2)
        results = []

        def generate():
            try:
                client = Client(raise_request_exception=False)
                client.force_login(self.sales)
                barrier.wait(timeout=10)
                response = client.post(reverse("quotation-generate"), {"enquiry": self.enquiry.pk,
                                       "idempotency_key": "concurrent"}, content_type=JSON)
                results.append((response.status_code, response.json().get("id")))
            finally:
                connections.close_all()

        threads = [threading.Thread(target=generate) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=20)
        self.assertEqual(len(results), 2)
        self.assertEqual([code for code, _ in results], [201, 201])
        self.assertEqual(results[0][1], results[1][1])
        self.assertEqual(QuoteRevision.objects.count(), 1)
