"""
F07 - what the money rules have to prove.

The things that would actually cost the company: billing a deposit
twice, banking one bank reference twice, letting an invoice be overpaid,
and dispatching goods before the advance has really arrived.
"""

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.core.api import business_date
from apps.quotations.test_acceptance import signature_file
from apps.quotations.models import QuoteRevision, QuoteStatus
from apps.quotations.tests import seed_quote_context

from .models import Invoice, InvoiceKind, Order, OrderStatus, Payment, PaymentStatus

User = get_user_model()
JSON = "application/json"


class OrderTestCase(TestCase):
    """Gets as far as an accepted quotation, which is where F07 starts."""

    def setUp(self):
        (self.admin, self.sales, self.technician,
         self.enquiry, self.survey, self.package) = seed_quote_context()
        self.finance = User.objects.create_user("order_finance", roles=[Role.FINANCE])

        self.client.force_login(self.sales)
        quote = self.client.post(
            reverse("quotation-generate"),
            {"enquiry": self.enquiry.pk, "idempotency_key": "gen"},
            content_type=JSON,
        ).json()
        self.quote = self.client.post(
            reverse("quotation-action", args=[quote["id"], "issue"]),
            {"revision": quote["revision"], "idempotency_key": "issue"},
            content_type=JSON,
        ).json()
        self.client.post(
            reverse("quotation-accept", args=[self.quote["id"]]),
            {"revision": self.quote["revision"], "idempotency_key": "accept",
             "customer_name": "Ramesh Gupta", "signature": signature_file()},
        )

    def confirm(self):
        response = self.client.post(
            reverse("order-confirm"), {"quotation": self.quote["id"]}, content_type=JSON
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()

    def pay(self, order, amount, *, method="upi", reference="UPI-1",
            status=PaymentStatus.CLEARED):
        self.client.force_login(self.finance)
        return self.client.post(
            reverse("payment-create", args=[order["id"]]),
            {"amount": str(amount), "method": method, "external_reference": reference,
             "status": status, "paid_on": str(business_date())},
            content_type=JSON,
        )


class OrderConfirmationTests(OrderTestCase):
    def test_confirming_creates_the_order_and_asks_for_the_advance(self):
        order = self.confirm()

        self.assertTrue(order["reference"].startswith("ORD-"))
        self.assertEqual(order["status"], OrderStatus.CONFIRMED)
        self.assertEqual(order["gross_payable"], self.quote["gross_payable_incl_tax"])
        self.assertEqual(order["advance_payable"],
                         self.quote["terms"]["advance_amount_incl_tax"])

        invoice = Invoice.objects.get()
        self.assertEqual(invoice.kind, InvoiceKind.ADVANCE)
        self.assertEqual(str(invoice.amount), order["advance_payable"])

    def test_confirming_twice_returns_the_same_order(self):
        first = self.confirm()
        second = self.confirm()

        self.assertEqual(first["id"], second["id"])
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(Invoice.objects.count(), 1)

    def test_an_unaccepted_quotation_does_not_become_an_order(self):
        """A quotation still sitting with the customer is not a sale."""
        QuoteRevision.objects.filter(pk=self.quote["id"]).update(status=QuoteStatus.ISSUED)

        response = self.client.post(
            reverse("order-confirm"), {"quotation": self.quote["id"]}, content_type=JSON
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_a_deposit_is_never_billed_twice(self):
        order = self.confirm()

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.objects.create(
                    order=Order.objects.get(pk=order["id"]), kind=InvoiceKind.ADVANCE,
                    amount=Decimal("100.00"), issued_by=self.sales,
                    issued_at=timezone.now(),
                )


class PaymentTests(OrderTestCase):
    def test_only_cleared_money_opens_the_dispatch_gate(self):
        order = self.confirm()
        advance = Decimal(order["advance_payable"])

        self.pay(order, advance, status=PaymentStatus.PENDING)
        pending = self.client.get(reverse("order-detail", args=[order["id"]])).json()
        self.assertFalse(pending["advance_cleared"])
        self.assertFalse(pending["dispatch_allowed"])

        payment = Payment.objects.get()
        self.client.post(reverse("payment-clear", args=[payment.pk]),
                         {"revision": payment.revision}, content_type=JSON)

        cleared = self.client.get(reverse("order-detail", args=[order["id"]])).json()
        self.assertTrue(cleared["advance_cleared"])
        self.assertTrue(cleared["dispatch_allowed"])

    def test_the_same_bank_reference_cannot_be_banked_twice(self):
        order = self.confirm()

        first = self.pay(order, Decimal("100.00"), reference="NEFT-9981")
        second = self.pay(order, Decimal("100.00"), reference="NEFT-9981")

        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 400)
        self.assertEqual(Payment.objects.count(), 1)

    def test_money_cannot_be_recorded_as_having_moved_in_the_future(self):
        order = self.confirm()
        self.client.force_login(self.finance)

        response = self.client.post(
            reverse("payment-create", args=[order["id"]]),
            {"amount": "100.00", "method": "cash",
             "paid_on": str(business_date() + timedelta(days=1))},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 400)

    def test_a_payment_is_never_deleted(self):
        order = self.confirm()
        self.pay(order, Decimal("100.00"))

        with self.assertRaises(ValidationError):
            Payment.objects.get().delete()


class AllocationTests(OrderTestCase):
    def setUp(self):
        super().setUp()
        self.order = self.confirm()
        self.invoice = Invoice.objects.get()
        self.pay(self.order, self.invoice.amount, reference="UPI-ALLOC")
        self.payment = Payment.objects.get()

    def allocate(self, amount):
        return self.client.post(
            reverse("payment-allocate", args=[self.payment.pk]),
            {"invoice": self.invoice.pk, "amount": str(amount)},
            content_type=JSON,
        )

    def test_a_cleared_receipt_settles_its_invoice_with_no_second_step(self):
        """The common case takes no separate allocation."""
        self.invoice.refresh_from_db()
        self.payment.refresh_from_db()

        self.assertTrue(self.invoice.settled)
        self.assertEqual(self.payment.allocated_amount, self.payment.amount)

    def test_an_invoice_cannot_be_overpaid(self):
        """A second payment finds nothing owing and cannot be forced onto it."""
        self.pay(self.order, Decimal("500.00"), reference="UPI-EXTRA")
        spare = Payment.objects.exclude(pk=self.payment.pk).get()

        response = self.client.post(
            reverse("payment-allocate", args=[spare.pk]),
            {"invoice": self.invoice.pk, "amount": "500.00"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 400)
        self.invoice.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, self.invoice.amount)

    def test_an_unallocated_payment_stays_unallocated_until_there_is_an_invoice(self):
        self.pay(self.order, Decimal("500.00"), reference="UPI-ONACCOUNT")
        spare = Payment.objects.exclude(pk=self.payment.pk).get()

        self.assertEqual(spare.allocated_amount, Decimal("0.00"))

    def test_reversing_a_payment_releases_what_it_had_settled(self):
        self.payment.refresh_from_db()
        response = self.client.post(
            reverse("payment-reverse", args=[self.payment.pk]),
            {"revision": self.payment.revision, "reason": "Keyed against the wrong order"},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.invoice.refresh_from_db()
        self.payment.refresh_from_db()
        self.assertEqual(self.invoice.paid_amount, Decimal("0.00"))
        self.assertEqual(self.payment.status, PaymentStatus.REVERSED)
        self.assertEqual(self.payment.allocated_amount, Decimal("0.00"))

    def test_a_reversed_payment_no_longer_counts_as_money(self):
        self.client.post(
            reverse("payment-reverse", args=[self.payment.pk]),
            {"revision": self.payment.revision, "reason": "Duplicate entry"},
            content_type=JSON,
        )

        order = self.client.get(reverse("order-detail", args=[self.order["id"]])).json()
        self.assertEqual(Decimal(order["cleared_total"]), Decimal("0.00"))
        self.assertFalse(order["dispatch_allowed"])


class PermissionTests(OrderTestCase):
    def test_sales_cannot_record_money(self):
        order = self.confirm()
        self.client.force_login(self.sales)

        response = self.client.post(
            reverse("payment-create", args=[order["id"]]),
            {"amount": "100.00", "method": "cash", "paid_on": str(business_date())},
            content_type=JSON,
        )

        self.assertEqual(response.status_code, 403)

    def test_a_technician_cannot_see_orders(self):
        self.confirm()
        self.client.force_login(self.technician)

        response = self.client.get(reverse("order-list"))

        self.assertEqual(response.status_code, 403)
