"""
F14 - costs, technician hours and finance.

    TechnicianRate     - a cost rate from a date. Append-only.
    TimeEntry          - hours on a job, at the rate that applied.
    TechnicianPayment  - money paid against what has accrued.
    ProjectExpense     - a direct cost of one job.
    SupplierPayment    - money paid against a supplier's invoice.

Technician pay is an accrual ledger, not payroll (D025). A time entry
accrues a payable; a payment reduces it. Labour cost and labour payment
are two views of one piece of work, so only the entry is ever a cost.

Buying stock is not a project expense: stock is costed onto a job when
it is issued (services.py). Money is never corrected by editing it. A
mistake is reversed with a reason and the row stays on the ledger.

All amounts are INR and exclude tax unless the column says otherwise.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models


ZERO = Decimal("0.00")
SMALLEST_AMOUNT = Decimal("0.01")


class ReversibleEntry(models.Model):
    """What every money row here shares: a mistake leaves a trace."""

    reversed_reason = models.TextField(blank=True)
    reversed_at = models.DateTimeField(null=True, blank=True)
    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def delete(self, *args, **kwargs):
        raise ValidationError("Ledger rows are reversed, never deleted.")

    @property
    def is_reversed(self):
        return self.reversed_at is not None


# ============================================================
# Technician rates and time
# ============================================================

class TechnicianRate(models.Model):
    """A cost rate from a date. A change is a new row, like a product price."""

    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cost_rates"
    )
    rate_per_hour = models.DecimalField(
        max_digits=10, decimal_places=2, validators=[MinValueValidator(SMALLEST_AMOUNT)]
    )
    effective_from = models.DateField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="cost_rates_set"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-effective_from", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["technician", "effective_from"], name="one_rate_per_technician_per_date"
            ),
            models.CheckConstraint(
                condition=models.Q(rate_per_hour__gt=0), name="technician_rate_positive"
            ),
        ]

    def __str__(self):
        return f"{self.technician} at {self.rate_per_hour} from {self.effective_from}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Rates are append-only. Add one with a new effective date.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Rate history cannot be deleted.")


class TimeEntry(ReversibleEntry):
    """
    Hours one technician spent on one job on one day.

    The rate is copied in, so a later pay rise cannot rewrite what a
    finished job cost. Repeating a day on a job is refused rather than
    added up, because a resubmitted form must not accrue twice.
    """

    job = models.ForeignKey("scheduling.Job", on_delete=models.PROTECT, related_name="time_entries")
    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="time_entries"
    )
    work_date = models.DateField()
    hours = models.DecimalField(
        max_digits=5, decimal_places=2, validators=[MinValueValidator(SMALLEST_AMOUNT)]
    )
    rate_per_hour = models.DecimalField(max_digits=10, decimal_places=2)
    cost_amount = models.DecimalField(max_digits=12, decimal_places=2)
    note = models.CharField(max_length=300, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="time_entries_recorded"
    )

    class Meta:
        ordering = ["-work_date", "-id"]
        indexes = [models.Index(fields=["work_date"])]
        verbose_name_plural = "time entries"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hours__gt=0, hours__lte=24, cost_amount__gte=0),
                name="time_entry_within_a_day",
            ),
            models.UniqueConstraint(
                fields=["job", "technician", "work_date"],
                condition=models.Q(reversed_at__isnull=True),
                name="one_live_entry_per_technician_job_and_day",
            ),
        ]

    def __str__(self):
        return f"{self.hours} h by {self.technician} on {self.work_date}"


class TechnicianPayment(ReversibleEntry):
    """Money paid to a technician. Reduces the payable; it is not a cost."""

    technician = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pay_received"
    )
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(SMALLEST_AMOUNT)]
    )
    paid_on = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pay_recorded"
    )

    class Meta:
        ordering = ["-paid_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="technician_payment_positive"
            ),
        ]

    def __str__(self):
        return f"{self.amount} to {self.technician}"


# ============================================================
# Project and supplier money
# ============================================================

class ProjectExpense(ReversibleEntry):
    """A direct cost of one job, such as crane hire or a permit."""

    order = models.ForeignKey("orders.Order", on_delete=models.PROTECT, related_name="expenses")
    description = models.CharField(max_length=250)
    amount_excl_tax = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(SMALLEST_AMOUNT)]
    )
    incurred_on = models.DateField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expenses_recorded"
    )

    class Meta:
        ordering = ["-incurred_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_excl_tax__gt=0), name="project_expense_positive"
            ),
        ]

    def __str__(self):
        return f"{self.description} on {self.order_id}"


class SupplierPayment(ReversibleEntry):
    """Money paid against what a supplier invoiced. Tax-inclusive, as billed."""

    purchase_order = models.ForeignKey(
        "inventory.PurchaseOrder", on_delete=models.PROTECT, related_name="payments"
    )
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(SMALLEST_AMOUNT)]
    )
    paid_on = models.DateField()
    reference = models.CharField(max_length=100, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="supplier_payments"
    )

    class Meta:
        ordering = ["-paid_on", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount__gt=0), name="supplier_payment_positive"
            ),
        ]

    def __str__(self):
        return f"{self.amount} on purchase {self.purchase_order_id}"
