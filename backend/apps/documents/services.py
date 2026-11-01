"""
Generating and storing a document.

Generation is idempotent by content: regenerating a document whose
source has not changed returns the row that already exists, so a list
does not fill with identical files every time somebody presses
Download. A changed source writes a new row and keeps the old one,
because spec.md section 6 makes issued documents history.
"""

import hashlib
import json

from django.core.files.base import ContentFile
from django.db import transaction

from apps.quotations.services import document_content

from . import builders
from .models import Document, DocumentKind


# Bump when the way a document is drawn changes, so a layout fix
# produces a new file instead of handing back the old one. The hash is
# over what the document says, and how it says it is part of that.
RENDERER_VERSION = 2


def _digest(payload):
    """Stable hash of what the document asserts, and how it is drawn."""
    return hashlib.sha256(
        json.dumps(
            {"renderer": RENDERER_VERSION, "content": payload},
            sort_keys=True, default=str,
        ).encode("utf-8")
    ).hexdigest()


def _store(kind, reference, revision, content_hash, pdf, actor, **link):
    """
    Returns the existing document when the content is unchanged.

    The uniqueness that matters is the content, not the row: the same
    snapshot must not produce a second file.
    """
    existing = Document.objects.filter(
        kind=kind, content_hash=content_hash, **link
    ).first()
    if existing:
        return existing

    document = Document(
        kind=kind, reference=reference, revision=revision,
        content_hash=content_hash, generated_by=actor, **link,
    )
    document.file.save(
        f"{kind}-{reference}-{content_hash[:8]}.pdf", ContentFile(pdf), save=False
    )
    document.save()
    return document


# ============================================================
# One function per document
# ============================================================

@transaction.atomic
def generate_quotation(revision, actor):
    """
    Built from the frozen document content, so a quotation regenerated
    years later reproduces what was issued rather than today's prices.
    """
    content = document_content(revision)
    return _store(
        DocumentKind.QUOTATION, revision.quote.reference, revision.revision_number,
        _digest(content), builders.quotation_pdf(content), actor,
        quotation=revision,
    )


@transaction.atomic
def generate_invoice(invoice, actor):
    payload = {
        "reference": invoice.reference, "kind": invoice.kind,
        "amount": str(invoice.amount), "paid": str(invoice.paid_amount),
        "order": invoice.order.reference,
    }
    return _store(
        DocumentKind.INVOICE, invoice.reference, 1,
        _digest(payload), builders.invoice_pdf(invoice), actor,
        invoice=invoice,
    )


@transaction.atomic
def generate_receipt(payment, actor):
    payload = {
        "payment": payment.pk, "amount": str(payment.amount),
        "method": payment.method, "reference": payment.external_reference,
        "order": payment.order.reference,
    }
    return _store(
        DocumentKind.RECEIPT, payment.order.reference, 1,
        _digest(payload), builders.receipt_pdf(payment), actor,
        payment=payment,
    )


@transaction.atomic
def generate_handover(report, actor):
    acceptance = getattr(report, "acceptance", None)
    payload = {
        "order": report.job.order.reference,
        "capacity": str(report.installed_capacity_kw),
        "finished_at": str(report.finished_at),
        "units": sorted(
            report.installed_units.values_list("unit__asset_id", flat=True)
        ),
        "accepted": acceptance.pk if acceptance else None,
    }
    return _store(
        DocumentKind.HANDOVER, report.job.order.reference, 1,
        _digest(payload), builders.handover_pdf(report), actor,
        installation=report,
    )
