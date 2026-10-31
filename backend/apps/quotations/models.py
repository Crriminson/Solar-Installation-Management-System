"""Quotation series, frozen document revisions, generated lines and editable business defaults."""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


# ============================================================
# Configuration and document states
# ============================================================

class QuoteStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    ISSUED = "issued", "Issued"
    ACCEPTED = "accepted", "Accepted"
    REJECTED = "rejected", "Rejected"
    EXPIRED = "expired", "Expired"
    SUPERSEDED = "superseded", "Superseded"


class QuotationSettings(models.Model):
    """The singleton row is populated by migration and edited in the admin."""

    validity_days = models.PositiveIntegerField()
    advance_default_percent = models.DecimalField(max_digits=5, decimal_places=2)
    advance_min_percent = models.DecimalField(max_digits=5, decimal_places=2)
    advance_max_percent = models.DecimalField(max_digits=5, decimal_places=2)

    def clean(self):
        if self.pk != 1:
            raise ValidationError("Edit the existing quotation settings row.")
        if not self.validity_days:
            raise ValidationError("Validity must be at least one day.")
        if not 0 < self.advance_min_percent <= self.advance_default_percent <= self.advance_max_percent <= 100:
            raise ValidationError("Advance percentages must satisfy 0 < minimum ≤ default ≤ maximum ≤ 100.")


# ============================================================
# Quotation records
# ============================================================

class Quote(models.Model):
    enquiry = models.OneToOneField("customers.Enquiry", on_delete=models.PROTECT, related_name="quotation")
    reference = models.CharField(max_length=30, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]


class QuoteRevision(models.Model):
    quote = models.ForeignKey(Quote, on_delete=models.PROTECT, related_name="revisions")
    revision_number = models.PositiveIntegerField()
    revision = models.PositiveIntegerField(default=1)
    status = models.CharField(max_length=20, choices=QuoteStatus.choices, default=QuoteStatus.DRAFT)
    survey_revision = models.ForeignKey("surveys.SurveyRevision", on_delete=models.PROTECT)
    package_version = models.ForeignKey("catalogue.PackageVersion", on_delete=models.PROTECT)
    customer = models.ForeignKey("customers.Customer", on_delete=models.PROTECT)
    site = models.ForeignKey("customers.Site", on_delete=models.PROTECT)

    # Deliberate document snapshots: later address/catalogue edits cannot rewrite them.
    snapshot = models.JSONField()
    subsidy = models.JSONField(default=list)
    terms = models.JSONField()
    subtotal_excl_tax = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2)
    gross_payable_incl_tax = models.DecimalField(max_digits=14, decimal_places=2)
    validity_days = models.PositiveIntegerField()
    valid_until = models.DateField(null=True, blank=True)
    content_hash = models.CharField(max_length=64, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="quotes_created")
    issued_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="quotes_issued")
    issued_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-revision_number", "-id"]
        constraints = [
            models.UniqueConstraint(fields=["quote", "revision_number"], name="unique_quote_revision_number"),
            models.UniqueConstraint(fields=["quote"], condition=models.Q(status="draft"), name="one_draft_per_quote"),
            models.UniqueConstraint(fields=["quote"], condition=models.Q(status="issued"), name="one_issued_per_quote"),
            models.CheckConstraint(condition=models.Q(subtotal_excl_tax__gte=0, tax_amount__gte=0,
                                                     gross_payable_incl_tax=models.F("subtotal_excl_tax") + models.F("tax_amount")),
                                   name="quote_totals_reconcile"),
        ]

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("Quotation revisions are immutable. Use a quotation action or generate a new revision.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Quotation history cannot be deleted.")


class QuoteLine(models.Model):
    quotation = models.ForeignKey(QuoteRevision, on_delete=models.PROTECT, related_name="lines")
    product = models.ForeignKey("catalogue.Product", on_delete=models.PROTECT)
    price = models.ForeignKey("catalogue.ProductPrice", on_delete=models.PROTECT)
    sku = models.CharField(max_length=40)
    description = models.CharField(max_length=250)
    unit = models.CharField(max_length=20)
    quantity = models.DecimalField(max_digits=12, decimal_places=2)
    unit_price_excl_tax = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate_percent = models.DecimalField(max_digits=5, decimal_places=2)
    net_excl_tax = models.DecimalField(max_digits=14, decimal_places=2)
    tax_amount = models.DecimalField(max_digits=14, decimal_places=2)
    gross_incl_tax = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering = ["id"]
        constraints = [models.CheckConstraint(condition=models.Q(quantity__gt=0, unit_price_excl_tax__gte=0),
                                              name="quote_line_positive_quantity")]

    def save(self, *args, **kwargs):
        raise ValidationError("Lines are generated with the quotation and cannot be edited.")

    def delete(self, *args, **kwargs):
        raise ValidationError("Quotation lines cannot be deleted.")


class QuoteRequest(models.Model):
    """A unique key and payload hash make retries safe and detectable."""

    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    key = models.CharField(max_length=100)
    payload_hash = models.CharField(max_length=64)
    quotation = models.ForeignKey(QuoteRevision, on_delete=models.PROTECT)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["actor", "key"], name="unique_quote_request_key")]


# ============================================================
# Acceptance and signature (F06)
# ============================================================

class AcceptanceChannel(models.TextChoices):
    """How the customer was identified at the moment they signed."""

    SUPERVISED = "supervised", "Signed on a staff device"
    REMOTE = "remote", "Signed remotely over Telegram"


class Acceptance(models.Model):
    """
    Evidence that a named customer accepted one exact quotation revision.

    Written once and never edited. The order is built on this record, and
    it is what settles a later argument about what was agreed.

    Installation acceptance (F11) and service resolution (F13) are
    separate records. Neither implies this one.
    """

    quotation = models.OneToOneField(
        QuoteRevision, on_delete=models.PROTECT, related_name="acceptance"
    )
    channel = models.CharField(
        max_length=20,
        choices=AcceptanceChannel.choices,
        default=AcceptanceChannel.SUPERVISED,
    )
    customer_name = models.CharField(
        max_length=150,
        help_text="Typed by the customer, not copied off the record.",
    )
    signature = models.ImageField(upload_to="signatures/")

    # The document as it stood when signed. Re-hashing the quotation
    # later must reproduce this, or what was signed was something else.
    document_content_hash = models.CharField(max_length=64)

    # Supervised signing happens in front of somebody, and that person is
    # the evidence. A remote acceptance has no witness, so F16 records the
    # verified chat binding and its single-use token in place of one.
    witnessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="acceptances_witnessed",
    )

    # When the customer signed, which is not when the row was written.
    accepted_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(channel="remote") | models.Q(witnessed_by__isnull=False),
                name="supervised_acceptance_names_its_witness",
            ),
        ]

    def __str__(self):
        return f"{self.quotation.quote.reference} accepted by {self.customer_name}"

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("An acceptance record cannot be edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Acceptance evidence cannot be deleted.")
