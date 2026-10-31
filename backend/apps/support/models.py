"""
F13 - support, diagnosis, repair and replacement.

    ServiceTicket   - one complaint, from raising to customer confirmation.
    TicketAsset     - one affected unit and its warranty assessment.
    TicketPhoto     - captioned evidence of the fault.
    RepairEstimate  - priced work the customer has to approve (with lines).
    WorkLine        - parts and labour actually used, charged or not.
    Replacement     - a failed unit swapped for a new one.

Four working states, not eight (D048). A scheduled visit is an F10 job
pointing at the ticket, and waiting on a part is a block with an owner,
so neither needs a status of its own.

Eligibility is judged on when the complaint was recorded, never on when
somebody got to it (D021). A customer's claim of an earlier date is
recorded but does not count until an authorized person reviews it.

All amounts are INR. Columns say whether they include tax.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


ZERO = Decimal("0.00")
SMALLEST_QUANTITY = Decimal("0.01")


# ============================================================
# Choices
# ============================================================

class TicketStatus(models.TextChoices):
    NEW = "new", "New"
    DIAGNOSED = "diagnosed", "Diagnosed"
    IN_PROGRESS = "in_progress", "In progress"
    AWAITING_CONFIRMATION = "awaiting_confirmation", "Awaiting customer confirmation"
    CLOSED = "closed", "Closed"


ALLOWED_TICKET_MOVES = {
    TicketStatus.NEW: [TicketStatus.DIAGNOSED],
    TicketStatus.DIAGNOSED: [TicketStatus.IN_PROGRESS],
    TicketStatus.IN_PROGRESS: [TicketStatus.AWAITING_CONFIRMATION],
    # The customer decides: resolved closes it, not resolved sends it back.
    TicketStatus.AWAITING_CONFIRMATION: [TicketStatus.CLOSED, TicketStatus.IN_PROGRESS],
    TicketStatus.CLOSED: [TicketStatus.IN_PROGRESS],
}


class Priority(models.TextChoices):
    LOW = "low", "Low"
    NORMAL = "normal", "Normal"
    HIGH = "high", "High"


class Assessment(models.TextChoices):
    COVERED = "covered", "Covered by warranty"
    NOT_COVERED = "not_covered", "Not covered"
    REVIEW = "review", "Needs authorized review"


class EstimateStatus(models.TextChoices):
    PENDING = "pending", "Awaiting customer approval"
    APPROVED = "approved", "Approved by customer"
    DECLINED = "declined", "Declined by customer"
    SUPERSEDED = "superseded", "Superseded"


class Disposition(models.TextChoices):
    """What happened to the unit that came off the roof."""

    RETURNED = "returned", "Returned"
    QUARANTINED = "quarantined", "Quarantined"


# ============================================================
# Ticket
# ============================================================

class ServiceTicket(models.Model):
    """
    One complaint.

    Hangs off the order its equipment came on, because that is the order
    a repair invoice has to be raised against.
    """

    reference = models.CharField(max_length=30, unique=True, blank=True)
    status = models.CharField(
        max_length=25, choices=TicketStatus.choices, default=TicketStatus.NEW
    )
    priority = models.CharField(
        max_length=10, choices=Priority.choices, default=Priority.NORMAL
    )

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    site = models.ForeignKey("customers.Site", on_delete=models.PROTECT)
    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="tickets")

    fault_description = models.TextField()
    fault_code = models.CharField(max_length=50, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="owned_tickets",
    )

    # The server's clock, which is what eligibility is judged on (D021).
    complaint_at = models.DateTimeField()

    # An earlier date the customer claims, when they say so. Evidence for
    # a reviewer to weigh; it decides nothing by itself.
    claimed_complaint_at = models.DateTimeField(null=True, blank=True)

    # --- the technician's visit ---
    findings = models.TextField(blank=True)
    recommendation = models.TextField(blank=True)
    diagnosed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="tickets_diagnosed",
    )
    diagnosed_at = models.DateTimeField(null=True, blank=True)

    # Waiting on a part or an approval is a fact, not a state (D048).
    blocked_reason = models.TextField(blank=True)
    blocked_owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="blocked_tickets",
    )

    # --- closing ---
    confirmed_by_name = models.CharField(max_length=150, blank=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)

    idempotency_key = models.CharField(max_length=80, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="tickets_raised"
    )
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["status", "-id"])]
        constraints = [
            # A ticket closes on the customer's word, not the technician's.
            models.CheckConstraint(
                condition=~models.Q(status="closed") | ~models.Q(confirmed_by_name=""),
                name="closed_ticket_names_who_confirmed",
            ),
            models.CheckConstraint(
                condition=~models.Q(blocked_reason="") | models.Q(blocked_owner__isnull=True),
                name="blocked_ticket_has_an_owner",
            ),
            models.UniqueConstraint(
                fields=["idempotency_key"], condition=~models.Q(idempotency_key=""),
                name="one_ticket_per_idempotency_key",
            ),
        ]

    def __str__(self):
        return self.reference or f"Unsaved ticket for {self.customer_id}"

    def save(self, *args, **kwargs):
        if self.reference:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            super().save(*args, **kwargs)
            self.reference = f"TKT-{self.created_at.year}-{self.id:05d}"
            super().save(update_fields=["reference"])

    def delete(self, *args, **kwargs):
        raise ValidationError("Tickets are closed, never deleted.")

    @property
    def is_blocked(self):
        return bool(self.blocked_reason)


class TicketAsset(models.Model):
    """One affected unit. A ticket may concern several (spec.md section 8)."""

    ticket = models.ForeignKey(ServiceTicket, on_delete=models.PROTECT, related_name="assets")
    unit = models.ForeignKey(
        "inventory.SerializedUnit", on_delete=models.PROTECT, related_name="ticket_assets"
    )
    warranty = models.ForeignKey(
        "warranties.AssetWarranty", on_delete=models.PROTECT, null=True, blank=True,
        related_name="ticket_assets",
    )
    assessment = models.CharField(max_length=20, choices=Assessment.choices)

    # A reviewer's decision on a disputed or backdated claim.
    review_reason = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="ticket_reviews",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(fields=["ticket", "unit"], name="one_entry_per_unit_per_ticket"),
            models.CheckConstraint(
                condition=models.Q(reviewed_by__isnull=True) | ~models.Q(review_reason=""),
                name="assessment_review_states_its_reason",
            ),
        ]

    def __str__(self):
        return f"{self.unit_id} on {self.ticket_id}"

    @property
    def is_covered(self):
        return self.assessment == Assessment.COVERED


class TicketPhoto(models.Model):
    ticket = models.ForeignKey(ServiceTicket, on_delete=models.PROTECT, related_name="photos")
    image = models.ImageField(upload_to="ticket_photos/")
    caption = models.CharField(max_length=200)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="ticket_photos"
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.caption


# ============================================================
# Estimate
# ============================================================

class RepairEstimate(models.Model):
    """
    Priced work on uncovered equipment, for the customer to decide on.

    Approval is a recorded decision with a name and a time. No second
    signature is needed for a repair (spec.md F13). Going past an
    approved figure takes a new estimate and a fresh decision.
    """

    ticket = models.ForeignKey(ServiceTicket, on_delete=models.PROTECT, related_name="estimates")
    number = models.PositiveIntegerField()
    status = models.CharField(
        max_length=20, choices=EstimateStatus.choices, default=EstimateStatus.PENDING
    )
    net_excl_tax = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2)
    gross_incl_tax = models.DecimalField(max_digits=14, decimal_places=2)

    decided_by_name = models.CharField(max_length=150, blank=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="estimates_recorded"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-number"]
        constraints = [
            models.UniqueConstraint(fields=["ticket", "number"], name="one_estimate_number_per_ticket"),
            # Two live figures would leave "what did they approve?" unanswerable.
            models.UniqueConstraint(
                fields=["ticket"], condition=models.Q(status__in=["pending", "approved"]),
                name="one_live_estimate_per_ticket",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=["pending", "superseded"])
                | ~models.Q(decided_by_name=""),
                name="estimate_decision_names_the_customer",
            ),
        ]

    def __str__(self):
        return f"Estimate {self.number} on {self.ticket_id}"


class EstimateLine(models.Model):
    """One priced item, copied so a later price change cannot alter it."""

    estimate = models.ForeignKey(RepairEstimate, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey("catalogue.Product", on_delete=models.PROTECT)
    sku = models.CharField(max_length=40)
    description = models.CharField(max_length=250)
    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(SMALLEST_QUANTITY)]
    )
    unit_price_excl_tax = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate_percent = models.DecimalField(max_digits=5, decimal_places=2)
    net_excl_tax = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0, unit_price_excl_tax__gte=0),
                name="estimate_line_positive",
            ),
        ]

    def __str__(self):
        return f"{self.quantity} {self.unit} of {self.sku}"


# ============================================================
# Work actually done
# ============================================================

class WorkLine(models.Model):
    """
    Parts or labour used on one affected unit.

    Covered work charges the customer zero, but unit_cost is still kept:
    a warranty repair costs the company money and the job has to show it.
    Labour's internal cost comes from time entries (F14), so unit_cost is
    zero on a labour line. Counting it here too would count it twice.
    """

    ticket = models.ForeignKey(ServiceTicket, on_delete=models.PROTECT, related_name="work_lines")
    asset = models.ForeignKey(TicketAsset, on_delete=models.PROTECT, related_name="work_lines")
    product = models.ForeignKey("catalogue.Product", on_delete=models.PROTECT)
    sku = models.CharField(max_length=40)
    description = models.CharField(max_length=250)
    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(SMALLEST_QUANTITY)]
    )

    # What the customer pays. Both zero on covered work.
    charge_excl_tax = models.DecimalField(max_digits=14, decimal_places=2)
    charge_tax = models.DecimalField(max_digits=14, decimal_places=2)

    # What it cost us per unit. Restricted, per rules.md section 4.
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)

    # Set once billed, so no line can reach the customer twice.
    invoice = models.ForeignKey(
        "orders.Invoice", on_delete=models.PROTECT, null=True, blank=True,
        related_name="work_lines",
    )

    # A mis-entry is voided with a reason rather than erased.
    voided_reason = models.TextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="work_lines"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0, charge_excl_tax__gte=0, charge_tax__gte=0,
                                   unit_cost__gte=0),
                name="work_line_positive",
            ),
        ]

    def __str__(self):
        return f"{self.quantity} {self.unit} of {self.sku}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Work lines are voided, never deleted.")

    @property
    def is_void(self):
        return bool(self.voided_reason)

    @property
    def cost_total(self):
        return self.quantity * self.unit_cost


class Replacement(models.Model):
    """
    A failed unit swapped for a new one, linked to this ticket.

    The installation link is the old unit's own, so nothing is copied.
    new_warranty is empty on a paid replacement, which has no cover to
    move across.
    """

    ticket = models.ForeignKey(ServiceTicket, on_delete=models.PROTECT, related_name="replacements")
    asset = models.OneToOneField(TicketAsset, on_delete=models.PROTECT, related_name="replacement")
    old_unit = models.ForeignKey(
        "inventory.SerializedUnit", on_delete=models.PROTECT, related_name="replaced_as_old"
    )
    new_unit = models.OneToOneField(
        "inventory.SerializedUnit", on_delete=models.PROTECT, related_name="replacement_for"
    )
    disposition = models.CharField(max_length=20, choices=Disposition.choices)
    new_warranty = models.OneToOneField(
        "warranties.AssetWarranty", on_delete=models.PROTECT, null=True, blank=True,
        related_name="replacement_record",
    )
    reason = models.TextField()
    replaced_at = models.DateTimeField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="replacements_recorded"
    )

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return f"{self.old_unit_id} replaced by {self.new_unit_id}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("A replacement is a record of an event; it is not edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Replacement history cannot be deleted.")
