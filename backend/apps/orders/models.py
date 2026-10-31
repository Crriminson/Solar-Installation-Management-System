"""
F07 - orders, payments and invoices.

An accepted quotation becomes an order, and the order is what the money
hangs off. Four records:

    Order       - one per accepted quotation. Holds the agreed terms.
    Invoice     - a demand for part of the order's value.
    Payment     - money that moved, in either direction.
    Allocation  - which payment settled which invoice, and by how much.

Money is never corrected by editing it. A mis-entry is reversed and a
real return of money is a refund, so the ledger always shows what
happened rather than what somebody wishes had happened.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


ZERO = Decimal("0.00")
SMALLEST_AMOUNT = Decimal("0.01")


# ============================================================
# Choices
# ============================================================

class OrderStatus(models.TextChoices):
    CONFIRMED = "confirmed", "Confirmed"
    DELIVERED = "delivered", "Delivered"
    COMPLETED = "completed", "Completed"
    CANCELLED = "cancelled", "Cancelled"


class PaymentPlan(models.TextChoices):
    ADVANCE = "advance", "Advance then balance"
    FULL = "full", "Full payment up front"


class InvoiceKind(models.TextChoices):
    ADVANCE = "advance", "Advance"
    BALANCE = "balance", "Balance"
    FULL = "full", "Full amount"
    ZERO_CHARGE = "zero_charge", "Zero charge (warranty work)"


class PaymentKind(models.TextChoices):
    """Direction the money moved."""

    RECEIPT = "receipt", "Received from customer"
    REFUND = "refund", "Returned to customer"


class PaymentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    CLEARED = "cleared", "Cleared"
    REVERSED = "reversed", "Reversed"


class PaymentMethod(models.TextChoices):
    CASH = "cash", "Cash"
    UPI = "upi", "UPI"
    BANK_TRANSFER = "bank_transfer", "Bank transfer"
    CHEQUE = "cheque", "Cheque"
    CARD = "card", "Card"


# Only a cleared payment counts as money. Pending has not arrived, and
# reversed never really did.
SETTLING_STATUS = PaymentStatus.CLEARED


# ============================================================
# Order
# ============================================================

class Order(models.Model):
    """
    The job the customer has agreed to buy.

    One per accepted quotation, enforced by the one-to-one: confirming
    twice returns the order that already exists rather than making a
    second one. The warehouse requirement and the installation job are
    created by F09 and F10 when those land.
    """

    quotation = models.OneToOneField(
        "quotations.QuoteRevision", on_delete=models.PROTECT, related_name="order"
    )
    reference = models.CharField(max_length=30, unique=True, blank=True)
    status = models.CharField(
        max_length=20, choices=OrderStatus.choices, default=OrderStatus.CONFIRMED
    )

    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    site = models.ForeignKey("customers.Site", on_delete=models.PROTECT)

    # Frozen from the quotation at confirmation. The quotation revision is
    # immutable so these cannot drift, but copying them keeps the order
    # readable without walking back through the document.
    payment_plan = models.CharField(max_length=20, choices=PaymentPlan.choices)
    gross_payable = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    advance_payable = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(ZERO)],
        help_text="What must clear before dispatch. Equals the gross on a full plan.",
    )

    # The balance falls due when delivery completes, not at installation
    # (D024). F09 sets this on delivery; null until then.
    balance_due_on = models.DateField(null=True, blank=True)

    confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="orders_confirmed"
    )
    confirmed_at = models.DateTimeField()
    cancelled_reason = models.TextField(blank=True)

    # Optimistic concurrency, same contract as quotation revisions.
    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(advance_payable__lte=models.F("gross_payable")),
                name="advance_within_order_value",
            ),
        ]

    def __str__(self):
        return self.reference or f"Unsaved order for quotation {self.quotation_id}"

    def save(self, *args, **kwargs):
        """Numbers the order on first insert, inside the caller's transaction."""
        if self.reference:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            super().save(*args, **kwargs)
            self.reference = f"ORD-{self.confirmed_at.year}-{self.id:05d}"
            super().save(update_fields=["reference"])

    def delete(self, *args, **kwargs):
        raise ValidationError("Orders are cancelled, never deleted.")

    # --- money ---------------------------------------------------------

    def cleared_total(self):
        """Receipts that have cleared, less refunds that have cleared."""
        rows = self.payments.filter(status=SETTLING_STATUS)
        received = rows.filter(kind=PaymentKind.RECEIPT).aggregate(
            total=models.Sum("amount"))["total"] or ZERO
        refunded = rows.filter(kind=PaymentKind.REFUND).aggregate(
            total=models.Sum("amount"))["total"] or ZERO
        return received - refunded

    def outstanding(self):
        return self.gross_payable - self.cleared_total()

    @property
    def advance_cleared(self):
        return self.cleared_total() >= self.advance_payable

    @property
    def dispatch_allowed(self):
        """
        The money half of the dispatch gate.

        F09 adds the stock conditions and both have to hold. A cancelled
        order never dispatches, whatever has been paid.
        """
        return self.status == OrderStatus.CONFIRMED and self.advance_cleared


# ============================================================
# Invoice
# ============================================================

class Invoice(models.Model):
    """
    A demand for part of the order's value.

    paid_amount is kept here rather than summed on demand, so the
    database itself can refuse to let an invoice be overpaid.
    """

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="invoices")
    reference = models.CharField(max_length=30, unique=True, blank=True)
    kind = models.CharField(max_length=20, choices=InvoiceKind.choices)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    paid_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="invoices_issued"
    )
    issued_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            # A deposit is billed once. Without this a second advance
            # invoice would quietly double what the customer is asked for.
            models.UniqueConstraint(
                fields=["order", "kind"],
                condition=~models.Q(kind="zero_charge"),
                name="one_invoice_per_order_and_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(paid_amount__lte=models.F("amount")),
                name="invoice_not_overpaid",
            ),
            models.CheckConstraint(
                condition=models.Q(paid_amount__gte=ZERO),
                name="invoice_paid_amount_not_negative",
            ),
        ]

    def __str__(self):
        return self.reference or f"Unsaved {self.kind} invoice"

    def save(self, *args, **kwargs):
        if self.reference:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            super().save(*args, **kwargs)
            self.reference = f"INV-{self.issued_at.year}-{self.id:05d}"
            super().save(update_fields=["reference"])

    def delete(self, *args, **kwargs):
        raise ValidationError("Invoices are credited or reversed, never deleted.")

    @property
    def settled(self):
        return self.paid_amount >= self.amount


# ============================================================
# Payment
# ============================================================

class Payment(models.Model):
    """
    Money that moved, recorded by a staff member.

    There is no gateway and no bank feed (D019), so every row is
    somebody's deliberate entry. allocated_amount is kept here so the
    database can refuse to let one payment settle more than it is worth.
    """

    order = models.ForeignKey(Order, on_delete=models.PROTECT, related_name="payments")
    kind = models.CharField(
        max_length=20, choices=PaymentKind.choices, default=PaymentKind.RECEIPT
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(SMALLEST_AMOUNT)]
    )
    allocated_amount = models.DecimalField(max_digits=14, decimal_places=2, default=ZERO)
    method = models.CharField(max_length=20, choices=PaymentMethod.choices)
    external_reference = models.CharField(
        max_length=100, blank=True,
        help_text="UPI id, bank reference or cheque number, as printed.",
    )
    status = models.CharField(
        max_length=20, choices=PaymentStatus.choices, default=PaymentStatus.PENDING
    )

    # When the money moved, against when the office typed it in. Both are
    # kept, per spec.md section 6.
    paid_on = models.DateField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments_recorded"
    )

    reversed_reason = models.TextField(blank=True)
    revision = models.PositiveIntegerField(default=1)

    class Meta:
        ordering = ["-paid_on", "-id"]
        constraints = [
            # The same bank reference cannot be banked twice. Partial
            # index, because cash has no reference and those rows are blank.
            models.UniqueConstraint(
                fields=["method", "external_reference"],
                condition=~models.Q(external_reference=""),
                name="one_payment_per_method_and_reference",
            ),
            models.CheckConstraint(
                condition=models.Q(allocated_amount__lte=models.F("amount")),
                name="payment_not_over_allocated",
            ),
            models.CheckConstraint(
                condition=models.Q(allocated_amount__gte=ZERO),
                name="payment_allocated_amount_not_negative",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.amount}"

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Payments are reversed or refunded, never deleted. The ledger has "
            "to show what happened."
        )

    @property
    def unallocated(self):
        return self.amount - self.allocated_amount


# ============================================================
# Allocation
# ============================================================

class Allocation(models.Model):
    """Which payment settled which invoice, and by how much."""

    payment = models.ForeignKey(Payment, on_delete=models.PROTECT, related_name="allocations")
    invoice = models.ForeignKey(Invoice, on_delete=models.PROTECT, related_name="allocations")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(SMALLEST_AMOUNT)]
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["payment", "invoice"],
                name="one_allocation_per_payment_and_invoice",
            ),
        ]

    def __str__(self):
        return f"{self.amount} to {self.invoice_id}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Allocations are reversed with their payment, never deleted.")
