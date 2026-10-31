"""
Tests for F01 uploads, source attribution and phone search.

The upload field sits on a public form, so these prove a file is judged
by its contents rather than by what the sender says it is.
"""

import shutil
import tempfile

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Enquiry
from .tests import VALID_PAYLOAD

User = get_user_model()

PDF_BYTES = b"%PDF-1.7 a small bill"
SIZE_LIMIT_BYTES = 64


def make_file(name="bill.pdf", content=PDF_BYTES, content_type="application/pdf"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class UploadTestCase(TestCase):
    """Sends uploads to a temporary folder, removed after each test."""

    def setUp(self):
        cache.clear()
        media_root = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, media_root, ignore_errors=True)

        override = override_settings(MEDIA_ROOT=media_root)
        override.enable()
        self.addCleanup(override.disable)


class BillUploadTests(UploadTestCase):
    def submit(self, bill):
        return self.client.post(
            reverse("enquiry-create"), {**VALID_PAYLOAD, "electricity_bill": bill}
        )

    def test_a_pdf_bill_is_stored_with_the_enquiry(self):
        response = self.submit(make_file())

        self.assertEqual(response.status_code, 201)
        self.assertTrue(Enquiry.objects.get().electricity_bill)

    def test_a_program_is_refused(self):
        response = self.submit(
            make_file("run.exe", b"MZ program", "application/x-msdownload")
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("electricity_bill", response.json())

    def test_a_program_renamed_as_a_pdf_is_refused(self):
        """The name and declared type are the sender's to choose."""
        response = self.submit(make_file("bill.pdf", b"MZ program", "application/pdf"))

        self.assertEqual(response.status_code, 400)

    @override_settings(MAX_UPLOAD_SIZE_BYTES=SIZE_LIMIT_BYTES)
    def test_a_file_over_the_limit_is_refused(self):
        response = self.submit(make_file(content=PDF_BYTES * SIZE_LIMIT_BYTES))

        self.assertEqual(response.status_code, 400)

    def test_nothing_is_saved_when_the_bill_is_refused(self):
        self.submit(make_file("run.exe", b"MZ program"))

        self.assertEqual(Enquiry.objects.count(), 0)


class BillDownloadTests(UploadTestCase):
    def setUp(self):
        super().setUp()
        self.client.post(
            reverse("enquiry-create"),
            {**VALID_PAYLOAD, "electricity_bill": make_file()},
        )
        self.enquiry = Enquiry.objects.get()
        self.url = reverse("enquiry-bill", args=[self.enquiry.id])

    def test_a_visitor_cannot_download_a_bill(self):
        self.assertIn(self.client.get(self.url).status_code, [401, 403])

    def test_staff_can_download_a_bill(self):
        User.objects.create_user("sales", password="test-pass-123", roles=["sales"])
        self.client.login(username="sales", password="test-pass-123", roles=["sales"])

        response = self.client.get(self.url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(b"".join(response.streaming_content), PDF_BYTES)

    def test_an_enquiry_with_no_bill_returns_not_found(self):
        cache.clear()
        self.client.post(reverse("enquiry-create"), VALID_PAYLOAD)
        without_bill = Enquiry.objects.order_by("-id").first()
        User.objects.create_user("sales", password="test-pass-123", roles=["sales"])
        self.client.login(username="sales", password="test-pass-123", roles=["sales"])

        response = self.client.get(reverse("enquiry-bill", args=[without_bill.id]))

        self.assertEqual(response.status_code, 404)


class SourceAttributionTests(TestCase):
    def setUp(self):
        cache.clear()

    def submit_as_walk_in(self):
        return self.client.post(
            reverse("enquiry-create"), {**VALID_PAYLOAD, "source": "walk_in"}
        )

    def test_a_visitor_cannot_claim_another_source(self):
        self.submit_as_walk_in()

        self.assertEqual(Enquiry.objects.get().source, "web_form")

    def test_staff_can_record_where_an_enquiry_came_from(self):
        User.objects.create_user("sales", password="test-pass-123", roles=["sales"])
        self.client.login(username="sales", password="test-pass-123", roles=["sales"])

        self.submit_as_walk_in()

        self.assertEqual(Enquiry.objects.get().source, "walk_in")


class PhoneSearchTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client.post(reverse("enquiry-create"), VALID_PAYLOAD)
        User.objects.create_user("sales", password="test-pass-123", roles=["sales"])
        self.client.login(username="sales", password="test-pass-123", roles=["sales"])

    def count_for(self, search):
        response = self.client.get(reverse("enquiry-list"), {"search": search})
        return response.json()["count"]

    def test_a_number_is_found_however_it_is_typed(self):
        for typed in ["9876543210", "+91 98765 43210", "098765-43210", "98765 43210"]:
            self.assertEqual(self.count_for(typed), 1, typed)

    def test_a_different_number_finds_nothing(self):
        self.assertEqual(self.count_for("+91 90000 00000"), 0)
