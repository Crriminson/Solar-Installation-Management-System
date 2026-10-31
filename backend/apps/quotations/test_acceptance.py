"""
F06 - what acceptance has to prove.

A signature is only worth anything if it is tied to one exact document,
taken while that document was live, and impossible to edit afterwards.
"""

import io

from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from PIL import Image

from apps.core.api import business_date
from .models import Acceptance, QuoteRevision, QuoteStatus
from .tests import seed_quote_context

JSON = "application/json"


def signature_file(name="signature.png"):
    """A real PNG, because the upload validator reads the opening bytes."""
    buffer = io.BytesIO()
    Image.new("RGB", (240, 80), "white").save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.read(), content_type="image/png")


class AcceptanceTests(TestCase):
    def setUp(self):
        (self.admin, self.sales, self.technician,
         self.enquiry, self.survey, self.package) = seed_quote_context()
        self.client.force_login(self.sales)

    # --- helpers -------------------------------------------------------

    def issued_quote(self):
        response = self.client.post(
            reverse("quotation-generate"),
            {"enquiry": self.enquiry.pk, "idempotency_key": "gen"},
            content_type=JSON,
        )
        quote = response.json()
        issued = self.client.post(
            reverse("quotation-action", args=[quote["id"], "issue"]),
            {"revision": quote["revision"], "idempotency_key": "issue"},
            content_type=JSON,
        )
        return issued.json()

    def accept(self, quote, name="Ramesh Gupta", key="accept"):
        return self.client.post(
            reverse("quotation-accept", args=[quote["id"]]),
            {"revision": quote["revision"], "idempotency_key": key,
             "customer_name": name, "signature": signature_file()},
        )

    # --- the happy path ------------------------------------------------

    def test_accepting_records_the_signature_and_the_witness(self):
        quote = self.issued_quote()

        response = self.accept(quote)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["status"], QuoteStatus.ACCEPTED)

        acceptance = Acceptance.objects.get()
        self.assertEqual(acceptance.customer_name, "Ramesh Gupta")
        self.assertEqual(acceptance.witnessed_by, self.sales)
        self.assertEqual(acceptance.channel, "supervised")
        self.assertTrue(acceptance.signature.name)

    def test_the_signature_is_tied_to_the_document_that_was_issued(self):
        quote = self.issued_quote()

        self.accept(quote)

        acceptance = Acceptance.objects.get()
        quotation = QuoteRevision.objects.get(pk=quote["id"])
        self.assertEqual(acceptance.document_content_hash, quotation.content_hash)

    # --- the refusals --------------------------------------------------

    def test_a_draft_cannot_be_accepted(self):
        response = self.client.post(
            reverse("quotation-generate"),
            {"enquiry": self.enquiry.pk, "idempotency_key": "gen"},
            content_type=JSON,
        )
        draft = response.json()

        refused = self.accept(draft)

        self.assertEqual(refused.status_code, 400)
        self.assertFalse(Acceptance.objects.exists())

    def test_an_expired_quotation_cannot_be_accepted(self):
        quote = self.issued_quote()
        QuoteRevision.objects.filter(pk=quote["id"]).update(
            valid_until=business_date().replace(year=business_date().year - 1)
        )

        refused = self.accept(quote)

        self.assertEqual(refused.status_code, 400)
        self.assertFalse(Acceptance.objects.exists())

    def test_a_blank_customer_name_is_refused(self):
        quote = self.issued_quote()

        refused = self.client.post(
            reverse("quotation-accept", args=[quote["id"]]),
            {"revision": quote["revision"], "idempotency_key": "accept",
             "customer_name": "   ", "signature": signature_file()},
        )

        self.assertEqual(refused.status_code, 400)

    def test_a_file_that_is_not_an_image_is_refused(self):
        quote = self.issued_quote()
        pretend = SimpleUploadedFile("signature.png", b"not a png at all",
                                     content_type="image/png")

        refused = self.client.post(
            reverse("quotation-accept", args=[quote["id"]]),
            {"revision": quote["revision"], "idempotency_key": "accept",
             "customer_name": "Ramesh Gupta", "signature": pretend},
        )

        self.assertEqual(refused.status_code, 400)

    def test_acceptance_evidence_cannot_be_edited_or_deleted(self):
        quote = self.issued_quote()
        self.accept(quote)
        acceptance = Acceptance.objects.get()

        acceptance.customer_name = "Somebody Else"
        with self.assertRaises(ValidationError):
            acceptance.save()
        with self.assertRaises(ValidationError):
            acceptance.delete()

    def test_accepting_twice_does_not_make_a_second_record(self):
        quote = self.issued_quote()
        self.accept(quote)

        again = self.accept({"id": quote["id"], "revision": quote["revision"] + 1},
                            key="accept-again")

        self.assertEqual(again.status_code, 400)
        self.assertEqual(Acceptance.objects.count(), 1)

    # --- the restricted view -------------------------------------------

    def test_the_customer_view_shows_the_document_and_no_staff_actions(self):
        quote = self.issued_quote()

        response = self.client.get(reverse("quotation-present", args=[quote["id"]]))

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["reference"], quote["reference"])
        self.assertIn("lines", body)
        self.assertNotIn("actions", body)
        self.assertNotIn("survey_revision", body)
        self.assertNotIn("purchase_cost", str(body))
