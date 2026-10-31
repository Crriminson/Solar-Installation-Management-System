"""
F13 - what support, repair and replacement have to prove.

The expensive mistakes: a technician backlog expiring a valid claim,
work going ahead on money the customer never agreed to, covered work
billed or its cost lost, a replacement that leaves stock and warranty
disagreeing, and a ticket closed without the customer's word.
"""

import threading
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, connections, transaction
from django.test import Client, TestCase, TransactionTestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.catalogue.models import Category, Product, ProductPrice, TrackingMethod
from apps.core.api import business_date
from apps.customers.models import Customer, Site
from apps.inventory.models import MovementReason, SerializedUnit, StockStatus
from apps.orders.models import Invoice, InvoiceKind, PaymentStatus
from apps.quotations.test_acceptance import signature_file
from apps.scheduling.models import Job, JobStatus
from apps.warranties.models import AssetWarranty
from apps.warranties.tests import WarrantyFixture

from .models import (Assessment, EstimateStatus, Replacement, ServiceTicket, TicketAsset,
                     TicketStatus, WorkLine)

User = get_user_model()
JSON = "application/json"

PART_PRICE = Decimal("1000.00")
PART_COST = Decimal("600.00")
PART_GST = Decimal("18.00")
PART_GROSS = Decimal("1180.00")


class SupportFixture(WarrantyFixture):
    """A delivered order, a support desk, and a repair part to sell."""

    def setUp(self):
        super().setUp()
        self.support = User.objects.create_user("sup_desk", roles=[Role.SUPPORT])
        self.delivered()
        self.inverter = SerializedUnit.objects.get(product__sku="INV", order=self.order)
        self.part = Product.objects.create(
            sku="FUSE", name="Fuse", category=Category.PROTECTION,
            tracking_method=TrackingMethod.BULK, unit="piece", gst_rate_percent=PART_GST,
            is_repair_part=True,
        )
        ProductPrice.objects.create(
            product=self.part, selling_price_excl_tax=PART_PRICE,
            purchase_cost_excl_tax=PART_COST, effective_from=business_date(),
            created_by=self.manager,
        )

    # --- helpers -----------------------------------------------------------

    def expire_cover(self, unit=None):
        AssetWarranty.objects.filter(unit=unit or self.inverter).update(
            coverage_start=date(2020, 1, 1), coverage_expires_on=date(2022, 1, 1))

    def raise_ticket(self, *units, **fields):
        self.client.force_login(self.support)
        response = self.client.post(reverse("ticket-raise"), {
            "customer": self.order.customer_id,
            "units": [unit.pk for unit in (units or [self.inverter])],
            "fault_description": "Inverter shows a red light.", **fields,
        }, content_type=JSON)
        self.assertEqual(response.status_code, 201, response.content)
        return ServiceTicket.objects.get(pk=response.json()["id"])

    def act(self, ticket, action, actor=None, **body):
        ticket.refresh_from_db()
        self.client.force_login(actor or self.support)
        return self.client.post(
            reverse("ticket-action", args=[ticket.pk, action]),
            {"revision": ticket.revision, **body}, content_type=JSON,
        )

    def done(self, ticket, action, actor=None, **body):
        response = self.act(ticket, action, actor, **body)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def book_visit(self, ticket, technician=None):
        self.client.force_login(self.manager)
        # A day apart, because the overlap rule applies to these visits too.
        start = timezone.now() + timedelta(days=1 + Job.objects.count())
        response = self.client.post(reverse("ticket-visit", args=[ticket.pk]), {
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=2)).isoformat(),
            "technicians": [(technician or self.technician).pk],
        }, content_type=JSON)
        self.assertEqual(response.status_code, 201, response.content)
        return Job.objects.get(pk=response.json()["id"])

    def diagnosed(self, *units, **fields):
        ticket = self.raise_ticket(*units, **fields)
        job = self.book_visit(ticket)
        self.done(ticket, "diagnose", self.technician, job=job.pk,
                  findings="Fuse blown.", recommendation="Fit a new fuse.")
        return ticket

    def asset_of(self, ticket, unit=None):
        return TicketAsset.objects.get(ticket=ticket, unit=unit or self.inverter)

    def approve(self, ticket, quantity="1"):
        self.done(ticket, "estimate", lines=[{"product": self.part.pk, "quantity": quantity}])
        self.done(ticket, "decide-estimate", approved=True, customer_name="Ramesh Gupta")

    def in_progress(self, *units):
        """Diagnosed and started, approved first if anything is uncovered."""
        ticket = self.diagnosed(*units)
        if ticket.assets.filter(assessment=Assessment.NOT_COVERED).exists():
            self.approve(ticket)
        self.done(ticket, "start-work")
        return ticket

    def add_part(self, ticket, actor=None, quantity="1"):
        return self.act(ticket, "work-line", actor, asset=self.asset_of(ticket).pk,
                        product=self.part.pk, quantity=quantity)

    def stock_inverter(self, serial="INV-NEW"):
        return SerializedUnit.objects.create(
            product=self.inverter.product, goods_receipt=self.inverter.goods_receipt,
            serial_number=serial, acquisition_cost="7500.00", status=StockStatus.AVAILABLE,
        )


class SupportTestCase(SupportFixture, TestCase):
    pass


# ============================================================
# Finding a customer
# ============================================================

class LookupTests(SupportTestCase):
    def lookup(self, term):
        self.client.force_login(self.support)
        response = self.client.get(reverse("support-lookup"), {"q": term})
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def test_a_customer_is_found_by_name_phone_or_order(self):
        customer = self.order.customer

        for term in ["Quote Customer", customer.phone, self.order.reference]:
            self.assertIn(customer.pk, [row["id"] for row in self.lookup(term)["customers"]], term)

    def test_a_serial_shows_its_warranty_status_immediately(self):
        rows = self.lookup("INV-1")["assets"]

        self.assertEqual([row["asset_id"] for row in rows], [self.inverter.asset_id])
        self.assertEqual(rows[0]["status"], "in_cover")
        self.assertIn("last_covered_on", rows[0])

    def test_one_letter_searches_nothing(self):
        self.assertEqual(self.lookup("I"), {"customers": [], "assets": []})

    def test_a_customers_equipment_lists_cover_beside_each_unit(self):
        self.client.force_login(self.support)

        body = self.client.get(reverse("support-customer", args=[self.order.customer_id])).json()

        unit = next(row for row in body["units"] if row["id"] == self.inverter.pk)
        self.assertEqual(unit["warranty"]["status"], "in_cover")
        self.assertNotIn("acquisition_cost", str(body))


# ============================================================
# Raising and assessing
# ============================================================

class RaisingTests(SupportTestCase):
    def test_a_unit_in_cover_is_assessed_covered(self):
        ticket = self.raise_ticket()

        asset = self.asset_of(ticket)
        self.assertEqual(asset.assessment, Assessment.COVERED)
        self.assertEqual(asset.warranty.unit_id, self.inverter.pk)
        self.assertEqual(ticket.status, TicketStatus.NEW)
        self.assertTrue(ticket.reference.startswith("TKT-"))

    def test_a_unit_out_of_cover_is_assessed_not_covered(self):
        self.expire_cover()

        self.assertEqual(self.asset_of(self.raise_ticket()).assessment, Assessment.NOT_COVERED)

    def test_a_ticket_may_concern_several_units(self):
        panel = SerializedUnit.objects.filter(product__sku="PANEL", order=self.order).first()

        ticket = self.raise_ticket(self.inverter, panel)

        self.assertEqual(ticket.assets.count(), 2)

    def test_another_customers_unit_is_refused(self):
        other = Customer.objects.create(full_name="Someone Else", phone="9000000000")
        self.client.force_login(self.support)

        response = self.client.post(reverse("ticket-raise"), {
            "customer": other.pk, "units": [self.inverter.pk], "fault_description": "x",
        }, content_type=JSON)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(ServiceTicket.objects.exists())

    def test_the_same_form_submitted_twice_opens_one_ticket(self):
        first = self.raise_ticket(idempotency_key="form-1")
        second = self.raise_ticket(idempotency_key="form-1")

        self.assertEqual(first.pk, second.pk)
        self.assertEqual(ServiceTicket.objects.count(), 1)

    def test_a_claimed_date_in_the_future_is_refused(self):
        self.client.force_login(self.support)

        response = self.client.post(reverse("ticket-raise"), {
            "customer": self.order.customer_id, "units": [self.inverter.pk],
            "fault_description": "x",
            "claimed_complaint_at": (timezone.now() + timedelta(days=1)).isoformat(),
        }, content_type=JSON)

        self.assertEqual(response.status_code, 400)

    def test_a_backlog_cannot_expire_a_valid_claim(self):
        """D021: judged when raised, whatever the calendar says at the visit."""
        ticket = self.raise_ticket()
        self.expire_cover()
        job = self.book_visit(ticket)

        self.done(ticket, "diagnose", self.technician, job=job.pk,
                  findings="Fault confirmed.", recommendation="Replace the board.")
        self.done(ticket, "start-work")

        self.assertEqual(self.asset_of(ticket).assessment, Assessment.COVERED)


class ReviewTests(SupportTestCase):
    def setUp(self):
        super().setUp()
        self.expire_cover()
        self.ticket = self.diagnosed(claimed_complaint_at="2021-06-01T06:00:00Z")
        self.asset = self.asset_of(self.ticket)

    def review(self, actor, **body):
        self.ticket.refresh_from_db()
        self.client.force_login(actor)
        return self.client.post(reverse("ticket-review", args=[self.ticket.pk]), {
            "revision": self.ticket.revision, "asset": self.asset.pk,
            "assessment": Assessment.COVERED, "reason": "Call log confirms June.", **body,
        }, content_type=JSON)

    def test_a_backdated_claim_goes_to_review_rather_than_being_believed(self):
        self.assertEqual(self.asset.assessment, Assessment.REVIEW)

    def test_work_waits_for_the_review(self):
        response = self.act(self.ticket, "start-work")

        self.assertEqual(response.status_code, 400)
        self.assertIn("authorized review", str(response.content))

    def test_support_may_not_rule_on_a_claim(self):
        self.assertEqual(self.review(self.support).status_code, 403)

    def test_a_manager_rules_with_a_reason_on_the_record(self):
        response = self.review(self.manager)

        self.assertEqual(response.status_code, 200, response.content)
        self.asset.refresh_from_db()
        self.assertEqual(self.asset.assessment, Assessment.COVERED)
        self.assertEqual(self.asset.reviewed_by, self.manager)
        self.assertEqual(self.asset.review_reason, "Call log confirms June.")

    def test_a_ruling_needs_a_reason(self):
        self.assertEqual(self.review(self.manager, reason="  ").status_code, 400)

    def test_a_reviewed_claim_can_still_move_the_warranty(self):
        """The review is the authority here, though the date is out of cover."""
        self.review(self.manager)
        self.done(self.ticket, "start-work")
        spare = self.stock_inverter()

        response = self.act(self.ticket, "replace", asset=self.asset.pk, code=spare.asset_id,
                            disposition="quarantined", reason="Board failed")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(AssetWarranty.objects.filter(unit=spare, replaces__isnull=False).exists())

    def test_coverage_is_fixed_once_work_has_started(self):
        self.review(self.manager)
        self.done(self.ticket, "start-work")

        response = self.review(self.manager, assessment=Assessment.NOT_COVERED)

        self.assertEqual(response.status_code, 400)


# ============================================================
# Diagnosis
# ============================================================

class DiagnosisTests(SupportTestCase):
    def test_work_cannot_start_before_a_diagnosis(self):
        ticket = self.raise_ticket()

        self.assertEqual(self.act(ticket, "start-work").status_code, 400)

    def test_a_diagnosis_comes_from_a_visit_on_this_ticket(self):
        ticket = self.raise_ticket()
        other = self.raise_ticket()
        job = self.book_visit(other)

        response = self.act(ticket, "diagnose", self.technician, job=job.pk,
                            findings="x", recommendation="y")

        self.assertEqual(response.status_code, 404)

    def test_only_the_crew_on_the_visit_can_record_it(self):
        ticket = self.raise_ticket()
        job = self.book_visit(ticket)
        crew_of_one = User.objects.create_user("sup_tech2", roles=[Role.TECHNICIAN])
        self.book_visit(ticket, crew_of_one)

        response = self.act(ticket, "diagnose", crew_of_one, job=job.pk,
                            findings="x", recommendation="y")

        self.assertEqual(response.status_code, 400)
        self.assertIn("crew", str(response.content))

    def test_a_diagnosis_needs_a_recommendation(self):
        ticket = self.raise_ticket()
        job = self.book_visit(ticket)

        response = self.act(ticket, "diagnose", self.technician, job=job.pk,
                            findings="Fuse blown.", recommendation=" ")

        self.assertEqual(response.status_code, 400)

    def test_recording_a_diagnosis_puts_the_visit_in_progress(self):
        ticket = self.diagnosed()

        self.assertEqual(ticket.jobs.get().status, JobStatus.IN_PROGRESS)

    def test_a_cancelled_visit_cannot_support_a_diagnosis(self):
        ticket = self.raise_ticket()
        job = self.book_visit(ticket)
        Job.objects.filter(pk=job.pk).update(status=JobStatus.CANCELLED)

        response = self.act(ticket, "diagnose", self.manager, job=job.pk,
                            findings="x", recommendation="y")

        self.assertEqual(response.status_code, 400)


# ============================================================
# Covered work
# ============================================================

class CoveredWorkTests(SupportTestCase):
    def setUp(self):
        super().setUp()
        self.ticket = self.in_progress()
        self.add_part(self.ticket, self.technician)

    def test_covered_work_needs_no_estimate(self):
        self.assertEqual(self.ticket.estimates.count(), 0)

    def test_the_customer_is_charged_nothing(self):
        line = WorkLine.objects.get(ticket=self.ticket)

        self.assertEqual(line.charge_excl_tax, Decimal("0.00"))
        self.assertEqual(line.charge_tax, Decimal("0.00"))

    def test_finishing_raises_a_zero_charge_invoice(self):
        self.done(self.ticket, "finish", self.technician)

        invoice = Invoice.objects.get(ticket=self.ticket)
        self.assertEqual(invoice.kind, InvoiceKind.ZERO_CHARGE)
        self.assertEqual(invoice.amount, Decimal("0.00"))

    def test_the_internal_cost_stays_on_the_job(self):
        """Zero to the customer, never zero to the company."""
        self.done(self.ticket, "finish", self.technician)

        line = WorkLine.objects.get(ticket=self.ticket)
        self.assertEqual(line.unit_cost, PART_COST)
        self.assertEqual(line.cost_total, PART_COST)

    def test_a_covered_estimate_is_refused(self):
        response = self.act(self.ticket, "estimate",
                            lines=[{"product": self.part.pk, "quantity": "1"}])

        self.assertEqual(response.status_code, 400)

    def test_zero_charge_work_leaves_the_balance_alone(self):
        before = self.order.outstanding()

        self.done(self.ticket, "finish", self.technician)

        self.assertEqual(self.order.outstanding(), before)


# ============================================================
# Chargeable work
# ============================================================

class ChargeableWorkTests(SupportTestCase):
    def setUp(self):
        super().setUp()
        self.expire_cover()

    def test_work_cannot_start_until_the_customer_approves(self):
        ticket = self.diagnosed()
        self.done(ticket, "estimate", lines=[{"product": self.part.pk, "quantity": "1"}])

        response = self.act(ticket, "start-work")

        self.assertEqual(response.status_code, 400)
        self.assertIn("approve", str(response.content))

    def test_an_estimate_is_priced_from_configured_rates(self):
        ticket = self.diagnosed()

        body = self.done(ticket, "estimate", lines=[{"product": self.part.pk, "quantity": "2"}])

        estimate = body["estimates"][0]
        self.assertEqual(estimate["net_excl_tax"], "2000.00")
        self.assertEqual(estimate["tax_amount"], "360.00")
        self.assertEqual(estimate["gross_incl_tax"], "2360.00")

    def test_approval_is_a_decision_with_a_name_and_a_time(self):
        ticket = self.diagnosed()
        self.approve(ticket)

        estimate = ticket.estimates.get()
        self.assertEqual(estimate.status, EstimateStatus.APPROVED)
        self.assertEqual(estimate.decided_by_name, "Ramesh Gupta")
        self.assertIsNotNone(estimate.decided_at)

    def test_a_declined_estimate_does_not_open_the_work(self):
        ticket = self.diagnosed()
        self.done(ticket, "estimate", lines=[{"product": self.part.pk, "quantity": "1"}])
        self.done(ticket, "decide-estimate", approved=False, customer_name="Ramesh Gupta")

        self.assertEqual(self.act(ticket, "start-work").status_code, 400)

    def test_the_invoice_comes_from_the_work_done_not_the_estimate(self):
        ticket = self.diagnosed()
        self.approve(ticket, quantity="3")
        self.done(ticket, "start-work")
        self.add_part(ticket)

        self.done(ticket, "finish")

        invoice = Invoice.objects.get(ticket=ticket)
        self.assertEqual(invoice.kind, InvoiceKind.REPAIR)
        self.assertEqual(invoice.amount, PART_GROSS)

    def test_going_past_the_approved_scope_is_refused(self):
        ticket = self.in_progress()
        self.assertEqual(self.add_part(ticket).status_code, 200)

        response = self.add_part(ticket)

        self.assertEqual(response.status_code, 400)
        self.assertIn("new estimate", str(response.content))

    def test_a_fresh_approval_opens_the_extra_scope(self):
        ticket = self.in_progress()
        self.add_part(ticket)

        self.approve(ticket, quantity="2")

        self.assertEqual(self.add_part(ticket).status_code, 200)
        self.assertEqual(ticket.estimates.filter(status=EstimateStatus.SUPERSEDED).count(), 1)

    def test_a_pending_new_estimate_suspends_the_old_approval(self):
        ticket = self.in_progress()
        self.done(ticket, "estimate", lines=[{"product": self.part.pk, "quantity": "5"}])

        self.assertEqual(self.add_part(ticket).status_code, 400)

    def test_a_voided_line_is_kept_but_not_billed(self):
        ticket = self.in_progress()
        self.add_part(ticket)
        line = WorkLine.objects.get(ticket=ticket)

        self.done(ticket, "void-line", line=line.pk, reason="Wrong part")
        self.done(ticket, "finish")

        line.refresh_from_db()
        self.assertEqual(line.voided_reason, "Wrong part")
        self.assertFalse(Invoice.objects.filter(ticket=ticket).exists())

    def test_a_voided_line_frees_its_share_of_the_scope(self):
        ticket = self.in_progress()
        self.add_part(ticket)
        line = WorkLine.objects.get(ticket=ticket)
        self.done(ticket, "void-line", line=line.pk, reason="Wrong part")

        self.assertEqual(self.add_part(ticket).status_code, 200)

    def test_a_repair_invoice_is_owed_on_top_of_the_order(self):
        """Paying for a repair must not look like paying off the installation."""
        before = self.order.outstanding()
        ticket = self.in_progress()
        self.add_part(ticket)

        self.done(ticket, "finish")

        self.assertEqual(self.order.outstanding(), before + PART_GROSS)

    def test_a_repair_payment_settles_the_repair(self):
        ticket = self.in_progress()
        self.add_part(ticket)
        self.done(ticket, "finish")
        invoice = Invoice.objects.get(ticket=ticket)
        Invoice.objects.filter(order=self.order).exclude(pk=invoice.pk).update(paid_amount=0)
        self.client.force_login(self.finance)

        response = self.client.post(reverse("payment-create", args=[self.order.pk]), {
            "amount": str(PART_GROSS), "method": "upi", "external_reference": "UPI-REPAIR",
            "status": PaymentStatus.CLEARED, "paid_on": str(business_date()),
        }, content_type=JSON)

        self.assertEqual(response.status_code, 201, response.content)

    def test_reopening_never_charges_the_same_line_twice(self):
        """In real money, where a double charge would actually show."""
        ticket = self.diagnosed()
        self.approve(ticket, quantity="2")
        self.done(ticket, "start-work")
        self.add_part(ticket)
        self.done(ticket, "finish")
        self.done(ticket, "confirm", customer_name="Ramesh Gupta")
        self.done(ticket, "reopen", reason="Failed again")
        self.add_part(ticket)

        self.done(ticket, "finish")

        amounts = list(Invoice.objects.filter(ticket=ticket).order_by("id")
                       .values_list("amount", flat=True))
        self.assertEqual(amounts, [PART_GROSS, PART_GROSS])

    def test_one_order_can_have_more_than_one_repair(self):
        for _ in range(2):
            ticket = self.in_progress()
            self.add_part(ticket)
            self.done(ticket, "finish")

        self.assertEqual(Invoice.objects.filter(kind=InvoiceKind.REPAIR).count(), 2)


class MixedCoverageTests(SupportTestCase):
    def test_covered_and_uncovered_units_are_charged_separately(self):
        panel = SerializedUnit.objects.filter(product__sku="PANEL", order=self.order).first()
        self.expire_cover(panel)
        ticket = self.diagnosed(self.inverter, panel)
        self.approve(ticket)
        self.done(ticket, "start-work")

        self.done(ticket, "work-line", asset=self.asset_of(ticket).pk,
                  product=self.part.pk, quantity="1")
        self.done(ticket, "work-line", asset=self.asset_of(ticket, panel).pk,
                  product=self.part.pk, quantity="1")
        self.done(ticket, "finish")

        self.assertEqual(Invoice.objects.get(ticket=ticket).amount, PART_GROSS)


# ============================================================
# Replacement
# ============================================================

class ReplacementFlowTests(SupportTestCase):
    def setUp(self):
        super().setUp()
        self.spare = self.stock_inverter()

    def replace(self, ticket, **fields):
        body = {"asset": self.asset_of(ticket).pk, "code": self.spare.serial_number,
                "disposition": "quarantined", "reason": "Board failed", **fields}
        return self.act(ticket, "replace", **body)

    def test_a_covered_replacement_issues_returns_and_moves_the_warranty(self):
        ticket = self.in_progress()

        response = self.replace(ticket)

        self.assertEqual(response.status_code, 200, response.content)
        self.spare.refresh_from_db()
        self.inverter.refresh_from_db()
        self.assertEqual(self.spare.status, StockStatus.INSTALLED)
        self.assertEqual(self.spare.customer_id, self.order.customer_id)
        self.assertEqual(self.inverter.status, StockStatus.QUARANTINED)

        new_warranty = AssetWarranty.objects.get(unit=self.spare)
        old_warranty = AssetWarranty.objects.get(unit=self.inverter)
        self.assertEqual(new_warranty.replaces, old_warranty)
        self.assertEqual(new_warranty.coverage_expires_on, old_warranty.coverage_expires_on)

    def test_the_replacement_links_both_units_to_this_ticket(self):
        ticket = self.in_progress()
        self.replace(ticket)

        record = Replacement.objects.get(ticket=ticket)
        self.assertEqual(record.old_unit, self.inverter)
        self.assertEqual(record.new_unit, self.spare)
        self.assertEqual(record.new_warranty.unit, self.spare)

    def test_every_stock_change_writes_a_movement(self):
        ticket = self.in_progress()
        self.replace(ticket)

        reasons = list(self.spare.movements.order_by("id").values_list("reason", flat=True))
        self.assertEqual(reasons, [MovementReason.RESERVATION, MovementReason.DISPATCH,
                                   MovementReason.DELIVERY, MovementReason.INSTALLATION])
        self.assertTrue(self.inverter.movements.filter(reason=MovementReason.RETURN).exists())

    def test_a_returned_unit_stays_returned(self):
        ticket = self.in_progress()

        self.replace(ticket, disposition="returned")

        self.inverter.refresh_from_db()
        self.assertEqual(self.inverter.status, StockStatus.RETURNED)

    def test_covered_replacement_costs_the_company_and_not_the_customer(self):
        ticket = self.in_progress()
        self.replace(ticket)

        line = WorkLine.objects.get(ticket=ticket)
        self.assertEqual(line.charge_excl_tax, Decimal("0.00"))
        self.assertEqual(line.unit_cost, Decimal("7500.00"))

    def test_a_unit_not_in_stock_is_refused(self):
        ticket = self.in_progress()
        SerializedUnit.objects.filter(pk=self.spare.pk).update(status=StockStatus.RESERVED)

        response = self.replace(ticket)

        self.assertEqual(response.status_code, 400)
        self.assertIn("not in stock", str(response.content))
        self.assertFalse(WorkLine.objects.filter(ticket=ticket).exists())

    def test_a_unit_cannot_be_replaced_twice_on_one_ticket(self):
        ticket = self.in_progress()
        self.replace(ticket)

        response = self.replace(ticket, code=self.stock_inverter("INV-NEW-2").asset_id)

        self.assertEqual(response.status_code, 400)

    def test_replacement_waits_for_the_work_to_start(self):
        ticket = self.diagnosed()

        self.assertEqual(self.replace(ticket).status_code, 400)

    def test_a_paid_replacement_has_no_warranty_to_move(self):
        self.expire_cover()
        price = self.inverter.product.current_price().selling_price_excl_tax
        ticket = self.diagnosed()
        self.done(ticket, "estimate", lines=[
            {"product": self.inverter.product.pk, "quantity": "1"}])
        self.done(ticket, "decide-estimate", approved=True, customer_name="Ramesh Gupta")
        self.done(ticket, "start-work")

        response = self.replace(ticket)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(Replacement.objects.get(ticket=ticket).new_warranty)
        self.assertEqual(WorkLine.objects.get(ticket=ticket).charge_excl_tax, price)

    def test_a_paid_replacement_past_the_scope_moves_nothing(self):
        self.expire_cover()
        ticket = self.in_progress()
        self.add_part(ticket)

        response = self.replace(ticket)

        self.assertEqual(response.status_code, 400)
        self.assertIn("new estimate", str(response.content))
        self.spare.refresh_from_db()
        self.assertEqual(self.spare.status, StockStatus.AVAILABLE)

    def test_a_fitted_replacement_line_cannot_be_voided(self):
        ticket = self.in_progress()
        self.replace(ticket)
        line = WorkLine.objects.get(ticket=ticket)

        response = self.act(ticket, "void-line", line=line.pk, reason="Mistake")

        self.assertEqual(response.status_code, 400)


# ============================================================
# Closing
# ============================================================

class ClosingTests(SupportTestCase):
    def setUp(self):
        super().setUp()
        self.ticket = self.in_progress()

    def test_finishing_is_not_closing(self):
        self.done(self.ticket, "finish", self.technician)

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.AWAITING_CONFIRMATION)

    def test_finishing_ends_the_visit(self):
        self.done(self.ticket, "finish", self.technician)

        self.assertEqual(self.ticket.jobs.get().status, JobStatus.COMPLETED)

    def test_a_technician_cannot_close_a_ticket(self):
        self.done(self.ticket, "finish", self.technician)

        response = self.act(self.ticket, "confirm", self.technician, customer_name="Tech")

        self.assertEqual(response.status_code, 403)

    def test_closing_needs_the_customers_name(self):
        self.done(self.ticket, "finish")

        self.assertEqual(self.act(self.ticket, "confirm", customer_name=" ").status_code, 400)

    def test_a_ticket_cannot_jump_straight_to_closed(self):
        self.assertEqual(self.act(self.ticket, "confirm", customer_name="Ramesh").status_code, 400)

    def test_the_customers_word_closes_it(self):
        self.done(self.ticket, "finish")

        self.done(self.ticket, "confirm", customer_name="Ramesh Gupta")

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.CLOSED)
        self.assertEqual(self.ticket.confirmed_by_name, "Ramesh Gupta")
        self.assertIsNotNone(self.ticket.confirmed_at)

    def test_the_database_refuses_a_closed_ticket_with_no_confirmation(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            ServiceTicket.objects.filter(pk=self.ticket.pk).update(status=TicketStatus.CLOSED)

    def test_a_customer_who_is_not_satisfied_sends_it_back(self):
        self.done(self.ticket, "finish")

        self.done(self.ticket, "send-back", reason="Still shows red")

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_PROGRESS)

    def test_reopening_needs_a_reason(self):
        self.done(self.ticket, "finish")
        self.done(self.ticket, "confirm", customer_name="Ramesh Gupta")

        self.assertEqual(self.act(self.ticket, "reopen").status_code, 400)

    def test_reopening_keeps_the_old_confirmation_in_the_audit_trail(self):
        from apps.core.models import AuditEvent
        self.done(self.ticket, "finish")
        self.done(self.ticket, "confirm", customer_name="Ramesh Gupta")

        self.done(self.ticket, "reopen", reason="Failed again")

        self.ticket.refresh_from_db()
        self.assertEqual(self.ticket.status, TicketStatus.IN_PROGRESS)
        self.assertEqual(self.ticket.confirmed_by_name, "")
        event = AuditEvent.objects.get(action="reopened", record_id=self.ticket.pk)
        self.assertEqual(event.before["confirmed_by_name"], "Ramesh Gupta")
        self.assertEqual(event.reason, "Failed again")

    def test_going_round_again_bills_only_what_is_new(self):
        self.add_part(self.ticket)
        self.done(self.ticket, "finish")
        self.done(self.ticket, "confirm", customer_name="Ramesh Gupta")
        self.done(self.ticket, "reopen", reason="Failed again")
        self.add_part(self.ticket)

        self.done(self.ticket, "finish")

        self.assertEqual(Invoice.objects.filter(ticket=self.ticket).count(), 2)
        self.assertEqual(
            WorkLine.objects.filter(ticket=self.ticket, invoice__isnull=True).count(), 0)

    def test_nothing_billable_raises_no_invoice(self):
        self.done(self.ticket, "finish")

        self.assertFalse(Invoice.objects.filter(ticket=self.ticket).exists())


class BlockTests(SupportTestCase):
    def test_waiting_on_a_part_has_an_owner_and_a_reason(self):
        ticket = self.raise_ticket()

        body = self.done(ticket, "block", reason="Waiting on a fuse", owner=self.manager.pk)

        self.assertTrue(body["is_blocked"])
        self.assertEqual(body["blocked_owner"], self.manager.pk)
        self.assertEqual(body["status"], TicketStatus.NEW)

    def test_a_block_with_nobody_to_clear_it_is_refused(self):
        ticket = self.raise_ticket()

        self.assertEqual(self.act(ticket, "block", reason="x", owner=999999).status_code, 400)

    def test_clearing_a_block_leaves_the_status_alone(self):
        ticket = self.raise_ticket()
        self.done(ticket, "block", reason="Waiting", owner=self.manager.pk)

        self.assertFalse(self.done(ticket, "unblock")["is_blocked"])


class StaleEditTests(SupportTestCase):
    def test_a_stale_revision_is_refused(self):
        ticket = self.raise_ticket()
        revision = ticket.revision
        self.done(ticket, "block", reason="Waiting", owner=self.manager.pk)
        self.client.force_login(self.support)

        response = self.client.post(reverse("ticket-action", args=[ticket.pk, "unblock"]),
                                    {"revision": revision}, content_type=JSON)

        self.assertEqual(response.status_code, 409)


# ============================================================
# Permissions
# ============================================================

class TicketPermissionTests(SupportTestCase):
    def setUp(self):
        super().setUp()
        self.ticket = self.in_progress()
        self.add_part(self.ticket)

    def login_as(self, role):
        user = User.objects.create_user(f"sup_{role}", roles=[role])
        self.client.force_login(user)
        return user

    def test_support_and_oversight_can_read(self):
        for role in [Role.OPERATIONS_MANAGER, Role.FINANCE, Role.DIRECTOR, Role.SUPPORT]:
            self.login_as(role)
            self.assertEqual(
                self.client.get(reverse("ticket-detail", args=[self.ticket.pk])).status_code,
                200, role)

    def test_sales_and_warehouse_have_no_ticket_access(self):
        for role in [Role.SALES, Role.WAREHOUSE]:
            self.login_as(role)
            self.assertEqual(self.client.get(reverse("ticket-list")).status_code, 403, role)

    def test_anonymous_is_refused(self):
        self.client.logout()

        self.assertEqual(self.client.get(reverse("ticket-list")).status_code, 403)

    def test_a_technician_reaches_only_their_own_tickets(self):
        stranger = User.objects.create_user("sup_stranger", roles=[Role.TECHNICIAN])
        self.client.force_login(stranger)

        self.assertEqual(self.client.get(reverse("ticket-list")).json()["count"], 0)
        self.assertEqual(
            self.client.get(reverse("ticket-detail", args=[self.ticket.pk])).status_code, 404)
        self.assertEqual(self.act(self.ticket, "finish", stranger).status_code, 404)

    def test_a_technician_cannot_price_or_approve(self):
        for action in ["estimate", "decide-estimate", "assign", "reopen"]:
            self.assertEqual(self.act(self.ticket, action, self.technician).status_code, 403, action)

    def test_a_technician_cannot_look_up_customers(self):
        self.client.force_login(self.technician)

        self.assertEqual(self.client.get(reverse("support-lookup"), {"q": "Quote"}).status_code, 403)

    def test_readers_cannot_write(self):
        for role in [Role.FINANCE, Role.DIRECTOR]:
            self.assertEqual(self.act(self.ticket, "finish", self.login_as(role)).status_code,
                             403, role)

    def test_cost_is_for_those_allowed_to_see_it(self):
        self.client.force_login(self.support)
        hidden = self.client.get(reverse("ticket-detail", args=[self.ticket.pk])).json()
        self.client.force_login(self.finance)
        shown = self.client.get(reverse("ticket-detail", args=[self.ticket.pk])).json()

        self.assertNotIn("unit_cost", hidden["work_lines"][0])
        self.assertEqual(shown["work_lines"][0]["unit_cost"], str(PART_COST))

    def test_a_technician_sees_no_more_of_the_customer_than_the_job_needs(self):
        self.client.force_login(self.technician)

        body = self.client.get(reverse("ticket-detail", args=[self.ticket.pk])).json()

        self.assertNotIn("customer_phone", body)

    def test_the_list_does_not_run_a_query_per_row(self):
        self.client.force_login(self.support)
        with CaptureQueriesContext(connection) as few:
            self.client.get(reverse("ticket-list"))
        self.in_progress()
        self.in_progress()
        self.client.force_login(self.support)
        with CaptureQueriesContext(connection) as many:
            self.client.get(reverse("ticket-list"))

        self.assertEqual(len(few), len(many))

    def test_a_photo_is_captioned_and_validated(self):
        self.client.force_login(self.support)

        response = self.client.post(reverse("ticket-photos", args=[self.ticket.pk]),
                                    {"image": signature_file(), "caption": "Burnt board"})

        self.assertEqual(response.status_code, 201, response.content)
        self.assertEqual(self.ticket.photos.count(), 1)


class SiteTests(SupportTestCase):
    def test_a_ticket_takes_its_site_from_the_equipment(self):
        extra = Site.objects.create(customer=self.order.customer, address_line="Other", city="Pune",
                                    state="Maharashtra", pincode="411001")

        ticket = self.raise_ticket()

        self.assertNotEqual(ticket.site_id, extra.pk)
        self.assertEqual(ticket.site_id, self.order.site_id)


# ============================================================
# Concurrency, with real threads
# ============================================================

class SimultaneousTicketTests(SupportFixture, TransactionTestCase):
    def run_together(self, work, count=2):
        barrier = threading.Barrier(count)

        def run(index):
            try:
                work(index, barrier)
            finally:
                connections.close_all()

        threads = [threading.Thread(target=run, args=[index]) for index in range(count)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    def test_a_double_submitted_form_opens_one_ticket(self):
        codes = []

        def submit(_index, barrier):
            client = Client(raise_request_exception=False)
            client.force_login(self.support)
            barrier.wait()
            codes.append(client.post(reverse("ticket-raise"), {
                "customer": self.order.customer_id, "units": [self.inverter.pk],
                "fault_description": "Red light", "idempotency_key": "same-form",
            }, content_type=JSON).status_code)

        self.run_together(submit)

        self.assertEqual(codes, [201, 201])
        self.assertEqual(ServiceTicket.objects.count(), 1)

    def test_tickets_raised_by_different_people_at_once_are_both_kept(self):
        desks = [self.support, User.objects.create_user("sup_desk2", roles=[Role.SUPPORT])]
        codes = []

        def submit(index, barrier):
            client = Client(raise_request_exception=False)
            client.force_login(desks[index])
            barrier.wait()
            codes.append(client.post(reverse("ticket-raise"), {
                "customer": self.order.customer_id, "units": [self.inverter.pk],
                "fault_description": "Red light",
            }, content_type=JSON).status_code)

        self.run_together(submit)

        self.assertEqual(codes, [201, 201])
        references = ServiceTicket.objects.values_list("reference", flat=True)
        self.assertEqual(len(set(references)), 2)

    def test_two_people_finishing_one_ticket_bill_it_once(self):
        ticket = self.in_progress()
        self.add_part(ticket)
        ticket.refresh_from_db()
        codes = []

        def finish(_index, barrier):
            client = Client(raise_request_exception=False)
            client.force_login(self.support)
            barrier.wait()
            codes.append(client.post(reverse("ticket-action", args=[ticket.pk, "finish"]),
                                     {"revision": ticket.revision},
                                     content_type=JSON).status_code)

        self.run_together(finish)

        self.assertEqual(sorted(codes), [200, 409])
        self.assertEqual(Invoice.objects.filter(ticket=ticket).count(), 1)

    def test_two_replacements_for_one_spare_unit_have_one_winner(self):
        tickets = [self.in_progress(), self.in_progress()]
        for ticket in tickets:
            ticket.refresh_from_db()
        spare = self.stock_inverter()
        assets = [self.asset_of(ticket).pk for ticket in tickets]
        codes = []

        def replace(index, barrier):
            client = Client(raise_request_exception=False)
            client.force_login(self.support)
            barrier.wait()
            codes.append(client.post(reverse("ticket-action", args=[tickets[index].pk, "replace"]), {
                "asset": assets[index], "code": spare.asset_id,
                "disposition": "returned", "reason": "Failed",
            }, content_type=JSON).status_code)

        self.run_together(replace)

        self.assertEqual(sorted(codes), [200, 400])
        self.assertEqual(Replacement.objects.filter(new_unit=spare).count(), 1)
