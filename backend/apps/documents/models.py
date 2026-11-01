"""
F19 - the paperwork the customer actually asks for.

Each document is a PDF built from a record, stored against it, and
regenerable. It carries its reference, revision and the time it was
generated, so a file passed around later still says what it is.

The rule that matters: a document generated from a snapshot reproduces
that snapshot, never current catalogue data. An issued quotation keeps
the prices it was issued with however the price list moves afterwards,
so regenerating one years later must produce the same paper.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class DocumentKind(models.TextChoices):
    """The documents spec.md F19 names. The first three are the baseline."""

    QUOTATION = "quotation", "Quotation"
    INVOICE = "invoice", "Invoice"
    RECEIPT = "receipt", "Payment receipt"
    HANDOVER = "handover", "Installation handover"
    WARRANTY = "warranty", "Warranty certificate"


class Document(models.Model):
    """
    One generated PDF, held against the record it describes.

    The record is named by whichever link is set. They are separate
    columns rather than a generic relation so the database can still
    answer "every document for this order" with a join.
    """

    kind = models.CharField(max_length=20, choices=DocumentKind.choices)

    # Copied from the record so the row describes itself in a list, and
    # keeps describing it if the record is later archived.
    reference = models.CharField(max_length=40)
    revision = models.PositiveIntegerField(default=1)

    # What the document asserts, hashed. Two generations of the same
    # snapshot produce the same hash; a different hash means the source
    # changed, which for an issued document should never happen.
    content_hash = models.CharField(max_length=64)

    file = models.FileField(upload_to="documents/")

    quotation = models.ForeignKey(
        "quotations.QuoteRevision", on_delete=models.PROTECT,
        null=True, blank=True, related_name="documents",
    )
    invoice = models.ForeignKey(
        "orders.Invoice", on_delete=models.PROTECT,
        null=True, blank=True, related_name="documents",
    )
    payment = models.ForeignKey(
        "orders.Payment", on_delete=models.PROTECT,
        null=True, blank=True, related_name="documents",
    )
    installation = models.ForeignKey(
        "installations.InstallationReport", on_delete=models.PROTECT,
        null=True, blank=True, related_name="documents",
    )

    generated_at = models.DateTimeField(auto_now_add=True)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="documents_generated",
    )

    class Meta:
        ordering = ["-generated_at", "-id"]
        indexes = [models.Index(fields=["kind", "reference"])]
        constraints = [
            # A document with nothing to describe is not a document.
            models.CheckConstraint(
                condition=(
                    models.Q(quotation__isnull=False)
                    | models.Q(invoice__isnull=False)
                    | models.Q(payment__isnull=False)
                    | models.Q(installation__isnull=False)
                ),
                name="document_names_its_record",
            ),
        ]

    def __str__(self):
        return f"{self.get_kind_display()} {self.reference}"

    def delete(self, *args, **kwargs):
        """
        Spec.md section 6: issued documents are history. Regenerating
        writes a new row; nothing removes the old one.
        """
        raise ValidationError("A generated document cannot be deleted.")
