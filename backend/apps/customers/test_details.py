"""
Tests for F01 details completed after intake.

The form asks for little, so what the customer did not know is filled
in later by staff. These prove that edit keeps the form's rules, changes
only what was sent, refuses a stale screen, records every change, and
is closed to roles that may not write to an enquiry.
"""

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.test.client import MULTIPART_CONTENT, encode_multipart, BOUNDARY
from django.urls import reverse

from apps.accounts.models import Role
from apps.core.models import AuditEvent
from .models import EnquiryStatus, Enquiry
from .tests import VALID_PAYLOAD
from .test_uploads import UploadTestCase, make_file

User = get_user_model()
JSON = "application/json"

# Only what the shortened form insists on.
MINIMAL_PAYLOAD = {
    key: VALID_PAYLOAD[key]
    for key in ("full_name", "phone", "address_line", "city", "state", "pincode")
}


def details_events(enquiry):
    return AuditEvent.objects.filter(
        record_type="customers.enquiry", record_id=enquiry.pk, action="details_updated"
    )


class ReferenceForStaffTests(TestCase):
    """Staff open what they saved; a visitor learns no internal id."""

    def setUp(self):
        cache.clear()

    def test_staff_get_the_new_enquiry_id(self):
        self.client.force_login(User.objects.create_user("seller", roles=[Role.SALES]))
        reply = self.client.post(reverse("enquiry-create"), {**MINIMAL_PAYLOAD, "source": "phone"})
        self.assertEqual(reply.status_code, 201)
        self.assertEqual(reply.json()["id"], Enquiry.objects.get().id)

    def test_a_visitor_gets_the_reference_only(self):
        reply = self.client.post(reverse("enquiry-create"), MINIMAL_PAYLOAD)
        self.assertEqual(reply.status_code, 201)
        self.assertIn("reference", reply.json())
        self.assertNotIn("id", reply.json())


class DetailsTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.client.post(reverse("enquiry-create"), MINIMAL_PAYLOAD)
        self.enquiry = Enquiry.objects.get()
        self.sales = User.objects.create_user("seller", roles=[Role.SALES])
        self.client.force_login(self.sales)

    def edit(self, **changes):
        self.enquiry.refresh_from_db()
        return self.client.patch(
            reverse("enquiry-details", args=[self.enquiry.pk]),
            {"revision": self.enquiry.revision, **changes},
            content_type=JSON,
        )


class CompletingDetailsTests(DetailsTestCase):
    def test_details_land_on_the_record_that_holds_them(self):
        reply = self.edit(
            email="asha@example.com", customer_type="commercial",
            shadow_free_roof_area_sqm="42.50", requested_capacity_kw="3.00",
            monthly_consumption_kwh="310.00",
        )
        self.assertEqual(reply.status_code, 200, reply.content)

        self.enquiry.refresh_from_db()
        customer, site = self.enquiry.site.customer, self.enquiry.site
        self.assertEqual(customer.email, "asha@example.com")
        self.assertEqual(customer.customer_type, "commercial")
        self.assertEqual(str(site.shadow_free_roof_area_sqm), "42.50")
        self.assertEqual(str(self.enquiry.requested_capacity_kw), "3.00")
        self.assertEqual(reply.json()["revision"], self.enquiry.revision)

    def test_fields_not_sent_are_left_alone(self):
        """The form's defaults must never overwrite what is stored."""
        self.edit(customer_type="commercial", requested_system_type="off_grid")
        self.edit(monthly_consumption_kwh="200.00")

        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.site.customer.customer_type, "commercial")
        self.assertEqual(self.enquiry.requested_system_type, "off_grid")

    def test_every_change_is_recorded_with_old_and_new_values(self):
        self.edit(requested_capacity_kw="5.00", notes="Wants backup for the pump")

        event = details_events(self.enquiry).get()
        self.assertEqual(event.actor, self.sales)
        self.assertEqual(event.before["requested_capacity_kw"], "None")
        self.assertEqual(event.after["requested_capacity_kw"], "5.00")
        self.assertEqual(event.after["notes"], "Wants backup for the pump")

    def test_an_edit_that_changes_nothing_records_nothing(self):
        revision = self.enquiry.revision
        reply = self.edit(notes="")

        self.assertEqual(reply.status_code, 200)
        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.revision, revision)
        self.assertFalse(details_events(self.enquiry).exists())

    def test_name_phone_and_address_cannot_be_changed_here(self):
        """Duplicate detection compares them, so they need their own rule."""
        self.edit(full_name="Someone Else", phone="9000000000", address_line="1 Other Street")

        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.site.customer.full_name, MINIMAL_PAYLOAD["full_name"])
        self.assertEqual(self.enquiry.site.customer.phone, MINIMAL_PAYLOAD["phone"])
        self.assertEqual(self.enquiry.site.address_line, MINIMAL_PAYLOAD["address_line"])


class DetailsRulesTests(DetailsTestCase):
    def test_a_bill_amount_needs_its_billing_period(self):
        reply = self.edit(monthly_bill_amount="2400.00")

        self.assertEqual(reply.status_code, 400)
        self.assertIn("billing_period_start", reply.json())
        self.enquiry.refresh_from_db()
        self.assertIsNone(self.enquiry.monthly_bill_amount)

    def test_a_billing_period_already_stored_counts(self):
        """Rules are checked against the record, not just this request."""
        self.edit(billing_period_start="2026-09-01", billing_period_end="2026-09-30",
                  monthly_bill_amount="2400.00")
        reply = self.edit(monthly_bill_amount="2600.00")

        self.assertEqual(reply.status_code, 200, reply.content)

    def test_a_period_ending_before_the_stored_start_is_refused(self):
        self.edit(billing_period_start="2026-09-01", billing_period_end="2026-09-30")
        reply = self.edit(billing_period_end="2026-08-15")

        self.assertEqual(reply.status_code, 400)
        self.assertIn("billing_period_end", reply.json())

    def test_negative_values_are_refused_by_field(self):
        reply = self.edit(shadow_free_roof_area_sqm="-1")

        self.assertEqual(reply.status_code, 400)
        self.assertIn("shadow_free_roof_area_sqm", reply.json())


class DetailsConcurrencyTests(DetailsTestCase):
    def test_a_stale_screen_is_refused_and_nothing_is_saved(self):
        stale = self.enquiry.revision
        self.edit(notes="First edit")

        reply = self.client.patch(
            reverse("enquiry-details", args=[self.enquiry.pk]),
            {"revision": stale, "notes": "Second edit from an old screen"},
            content_type=JSON,
        )
        self.assertEqual(reply.status_code, 409)
        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.notes, "First edit")

    def test_the_revision_must_be_sent(self):
        reply = self.client.patch(
            reverse("enquiry-details", args=[self.enquiry.pk]),
            {"notes": "No revision"}, content_type=JSON,
        )
        self.assertEqual(reply.status_code, 400)
        self.assertIn("revision", reply.json())

    def test_a_lost_enquiry_is_history_and_is_not_changed(self):
        Enquiry.objects.filter(pk=self.enquiry.pk).update(
            status=EnquiryStatus.LOST, lost_reason="Bought elsewhere"
        )
        reply = self.edit(notes="Too late")

        self.assertEqual(reply.status_code, 400)
        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.notes, "")


class DetailsPermissionTests(DetailsTestCase):
    def test_roles_that_cannot_write_to_an_enquiry_are_refused(self):
        """A director reads the sales queue but does not change it."""
        for role in (Role.DIRECTOR, Role.WAREHOUSE, Role.TECHNICIAN):
            with self.subTest(role=role):
                self.client.force_login(User.objects.create_user(f"user-{role}", roles=[role]))
                self.assertEqual(self.edit(notes="Not mine to change").status_code, 403)

        self.enquiry.refresh_from_db()
        self.assertEqual(self.enquiry.notes, "")

    def test_an_operations_manager_may_complete_details(self):
        self.client.force_login(User.objects.create_user("ops", roles=[Role.OPERATIONS_MANAGER]))
        self.assertEqual(self.edit(notes="Gate code 1234").status_code, 200)

    def test_a_visitor_cannot_edit(self):
        self.client.logout()
        self.assertEqual(self.edit(notes="Anonymous").status_code, 403)


class DetailsBillTests(UploadTestCase):
    def setUp(self):
        super().setUp()
        self.client.post(reverse("enquiry-create"), MINIMAL_PAYLOAD)
        self.enquiry = Enquiry.objects.get()
        self.client.force_login(User.objects.create_user("seller", roles=[Role.SALES]))

    def upload(self, file):
        return self.client.patch(
            reverse("enquiry-details", args=[self.enquiry.pk]),
            encode_multipart(BOUNDARY, {"revision": self.enquiry.revision,
                                        "electricity_bill": file}),
            content_type=MULTIPART_CONTENT,
        )

    def test_a_bill_can_be_attached_later_and_is_not_copied_into_history(self):
        reply = self.upload(make_file())

        self.assertEqual(reply.status_code, 200, reply.content)
        self.assertTrue(reply.json()["has_electricity_bill"])
        event = details_events(self.enquiry).get()
        self.assertEqual(event.after, {"electricity_bill": "uploaded"})

    def test_the_full_staff_form_with_blanks_clears_values(self):
        """
        The screen sends every field as text, blanks included. A blank
        number or date must clear the value, not be refused as invalid.
        """
        Enquiry.objects.filter(pk=self.enquiry.pk).update(monthly_consumption_kwh="310.00")
        reply = self.client.patch(
            reverse("enquiry-details", args=[self.enquiry.pk]),
            encode_multipart(BOUNDARY, {
                "revision": self.enquiry.revision, "email": "", "customer_type": "residential",
                "requested_system_type": "undecided", "shadow_free_roof_area_sqm": "",
                "requested_capacity_kw": "4.00", "electricity_connection_number": "",
                "monthly_bill_amount": "", "monthly_consumption_kwh": "",
                "billing_period_start": "", "billing_period_end": "", "notes": "",
            }),
            content_type=MULTIPART_CONTENT,
        )

        self.assertEqual(reply.status_code, 200, reply.content)
        self.enquiry.refresh_from_db()
        self.assertIsNone(self.enquiry.monthly_consumption_kwh)
        self.assertEqual(str(self.enquiry.requested_capacity_kw), "4.00")
        self.assertEqual(set(details_events(self.enquiry).get().after),
                         {"monthly_consumption_kwh", "requested_capacity_kw"})

    def test_a_file_that_is_not_a_bill_is_refused(self):
        reply = self.upload(make_file("bill.pdf", b"MZ not really a pdf"))

        self.assertEqual(reply.status_code, 400)
        self.assertIn("electricity_bill", reply.json())
