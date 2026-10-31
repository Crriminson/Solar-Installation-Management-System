"""Generate whole quotation snapshots and perform locked, audited document actions."""

import hashlib
import json
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as ModelValidationError
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.catalogue.models import PackageTemplate, PackageVersion, VersionStatus
from apps.catalogue.sizing import SizingError, parts_list
from apps.core.api import Conflict, business_date, check_revision
from apps.core.models import record_event
from apps.customers.models import Enquiry
from apps.subsidies.calculation import estimate_subsidies
from apps.surveys.models import RevisionStatus, Survey

from .models import (Acceptance, AcceptanceChannel, QuotationSettings, Quote, QuoteLine,
                     QuoteRequest, QuoteRevision, QuoteStatus)

PAISE = Decimal("0.01")  # INR: round each line's net and tax half up to one paisa.
PERCENT = Decimal("100")
MAX_DOCUMENT_AMOUNT = Decimal("999999999999.99")  # Maximum INR amount in a 14-digit, 2-decimal field.


# ============================================================
# Generation
# ============================================================

def content_hash(value):
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


@transaction.atomic
def generate_quote(data, actor):
    """The enquiry lock serializes first creation, revision numbering and retry keys."""
    get_user_model().objects.select_for_update().get(pk=actor.pk)
    enquiry = Enquiry.objects.select_for_update(of=("self",)).select_related("site__customer").filter(pk=data["enquiry"]).first()
    if enquiry is None:
        raise ValidationError({"enquiry": ["No enquiry with that id."]})
    request_hash = content_hash(data)
    previous_request = QuoteRequest.objects.filter(actor=actor, key=data["idempotency_key"]).first()
    if previous_request:
        if previous_request.payload_hash != request_hash:
            raise Conflict("This idempotency key was already used with different inputs.")
        return previous_request.quotation
    if not enquiry.is_open:
        raise ValidationError({"enquiry": ["A lost enquiry cannot produce a quotation."]})
    survey = Survey.objects.select_for_update().filter(enquiry=enquiry).first()
    approved = survey.approved_revision if survey else None
    if approved is None:
        raise ValidationError({"survey": ["An approved survey revision is required."]})
    # Lock the template used by activation, so its active version cannot change mid-generation.
    template = PackageTemplate.objects.select_for_update().filter(
        kind=approved.recommended_system_type, capacity_kw=approved.recommended_capacity_kw,
    ).first()
    if template is None:
        raise ValidationError({"package": ["No package matches the approved system type and capacity."]})
    version = template.active_version
    require_reviewed_package(version)
    problems = version.problems()
    if problems:
        raise ValidationError({"package": problems})
    try:
        generated_parts = parts_list(version, approved)
    except (SizingError, ArithmeticError, TypeError) as exc:
        raise ValidationError({"measurements": [str(exc)]})
    generated_lines = price_lines(generated_parts)
    subsidy = estimate_subsidies(enquiry.site, approved, data.get("subsidy_facts", {}))
    config = QuotationSettings.objects.filter(pk=1).first()
    if config is None:
        raise ValidationError({"quotation_settings": ["Configure quotation validity and advance terms first."]})
    try:
        config.full_clean()
    except ModelValidationError as exc:
        raise ValidationError({"quotation_settings": exc.messages})
    subtotal = sum((line["net_excl_tax"] for line in generated_lines), Decimal("0.00"))
    tax = sum((line["tax_amount"] for line in generated_lines), Decimal("0.00"))
    gross = subtotal + tax
    if gross > MAX_DOCUMENT_AMOUNT:
        raise ValidationError({"amount": ["Calculated quotation exceeds the supported INR amount. Review prices and quantities."]})
    terms = payment_terms(data, config, gross)
    quote, _ = Quote.objects.get_or_create(enquiry=enquiry, defaults={
        "reference": f"QUO-{business_date().year}-{enquiry.pk:05d}",
    })
    latest = quote.revisions.first()
    if latest:
        if data.get("previous_revision") != latest.pk or data.get("revision") != latest.revision:
            raise Conflict("Review the latest quotation revision before generating another.")
        if latest.status == QuoteStatus.ACCEPTED:
            raise ValidationError({"quotation": ["Accepted quotations cannot be revised here."]})
    snapshot = quotation_snapshot(enquiry, approved, version)
    fields = dict(
        survey_revision=approved, package_version=version, customer=enquiry.site.customer,
        site=enquiry.site, snapshot=snapshot, subsidy=subsidy, terms=terms,
        subtotal_excl_tax=subtotal, tax_amount=tax, gross_payable_incl_tax=gross,
        validity_days=config.validity_days, created_by=actor,
    )
    if latest and latest.status == QuoteStatus.DRAFT:
        before = {"snapshot": latest.snapshot, "terms": latest.terms, "gross_payable_incl_tax": str(latest.gross_payable_incl_tax)}
        QuoteRevision.objects.filter(pk=latest.pk).update(**fields, revision=latest.revision + 1, updated_at=timezone.now())
        latest.lines.all().delete()
        latest.refresh_from_db()
        quotation = latest
        record_event(quotation, "draft_regenerated", actor, before=before, after={"snapshot": snapshot})
    else:
        quotation = QuoteRevision.objects.create(quote=quote, revision_number=latest.revision_number + 1 if latest else 1, **fields)
    QuoteLine.objects.bulk_create([QuoteLine(quotation=quotation, **line) for line in generated_lines])
    QuoteRequest.objects.create(actor=actor, key=data["idempotency_key"], payload_hash=request_hash, quotation=quotation)
    record_event(quotation, "generated", actor, after={"status": quotation.status,
                 "survey_revision": approved.pk, "package_version": version.pk, "gross_payable_incl_tax": str(gross)})
    return quotation


def require_reviewed_package(version):
    if version is None or version.status != VersionStatus.ACTIVE or not version.reviewed_by_id or not version.reviewed_at:
        raise ValidationError({"package": ["An active, owner-reviewed package version is required."]})


def price_lines(parts):
    """Freeze today's dated selling prices and GST; purchase cost never enters this document."""
    from apps.catalogue.models import ProductPrice
    today = business_date()
    prices = ProductPrice.objects.filter(product_id__in=[part.product.pk for part in parts], effective_from__lte=today).order_by("product_id", "-effective_from", "-id")
    current_prices = {}
    for price in prices:
        current_prices.setdefault(price.product_id, price)
    lines = []
    for part in parts:
        product = part.product
        price = current_prices.get(product.pk)
        if not product.is_active or price is None or price.selling_price_excl_tax < 0:
            raise ValidationError({"price": [f"{product.sku}: active product and current non-negative selling price required."]})
        if part.quantity is None or part.quantity <= 0 or not 0 <= product.gst_rate_percent <= PERCENT:
            raise ValidationError({"quantity": [f"{product.sku}: positive quantity and valid GST rate required."]})
        net = (part.quantity * price.selling_price_excl_tax).quantize(PAISE, rounding=ROUND_HALF_UP)
        tax = (net * product.gst_rate_percent / PERCENT).quantize(PAISE, rounding=ROUND_HALF_UP)
        lines.append({"product": product, "price": price, "sku": product.sku,
                      "description": product.name, "unit": product.unit, "quantity": part.quantity,
                      "unit_price_excl_tax": price.selling_price_excl_tax,
                      "gst_rate_percent": product.gst_rate_percent,
                      "net_excl_tax": net, "tax_amount": tax, "gross_incl_tax": net + tax})
    if not lines:
        raise ValidationError({"package": ["The package has no components."]})
    return lines


def payment_terms(data, config, gross):
    plan = data.get("payment_plan", "advance")
    percent = data.get("advance_percent", config.advance_default_percent) if plan == "advance" else PERCENT
    if not config.advance_min_percent <= percent <= config.advance_max_percent:
        raise ValidationError({"advance_percent": [f"Choose {config.advance_min_percent}–{config.advance_max_percent} percent."]})
    amount = (gross * percent / PERCENT).quantize(PAISE, rounding=ROUND_HALF_UP)
    return {"plan": plan, "advance_percent": str(percent), "advance_amount_incl_tax": str(amount),
            "balance_amount_incl_tax": str(gross - amount), "balance_due": "delivery_completion",
            "subsidy_deducted": False, "notes": data.get("terms_notes", "")}


def quotation_snapshot(enquiry, survey, version):
    site = enquiry.site
    customer = site.customer
    return {"customer": {"name": customer.full_name, "phone": customer.phone,
                         "email": customer.email, "type": customer.customer_type},
            "site": {"address": site.address_line, "city": site.city, "state": site.state, "pincode": site.pincode},
            "survey": {"id": survey.pk, "number": survey.revision_number, **survey.measurement_snapshot()},
            "package": {"id": version.pk, "name": version.template.name, "version": version.version_number,
                        "cable_waste_factor": str(version.cable_waste_factor),
                        "cable_termination_buffer_m": str(version.cable_termination_buffer_m),
                        "battery_depth_of_discharge": str(version.battery_depth_of_discharge)},
            "rounding": "Line net and GST rounded half up to INR 0.01; totals are sums of rounded lines."}


# ============================================================
# Document actions
# ============================================================

def document_content(quotation):
    fields = ("sku", "description", "unit", "quantity", "unit_price_excl_tax", "gst_rate_percent",
              "net_excl_tax", "tax_amount", "gross_incl_tax")
    return {"reference": quotation.quote.reference, "revision_number": quotation.revision_number,
            "snapshot": quotation.snapshot, "subsidy": quotation.subsidy, "terms": quotation.terms,
            "subtotal_excl_tax": str(quotation.subtotal_excl_tax), "tax_amount": str(quotation.tax_amount),
            "gross_payable_incl_tax": str(quotation.gross_payable_incl_tax),
            "valid_until": str(quotation.valid_until), "issued_at": str(quotation.issued_at),
            "lines": list(quotation.lines.values(*fields))}


@transaction.atomic
def quote_action(pk, action, data, actor):
    get_user_model().objects.select_for_update().get(pk=actor.pk)
    initial = QuoteRevision.objects.filter(pk=pk).first()
    if initial is None:
        from rest_framework.exceptions import NotFound
        raise NotFound()
    Enquiry.objects.select_for_update().get(pk=initial.quote.enquiry_id)
    Survey.objects.select_for_update().get(pk=initial.survey_revision.survey_id)
    Quote.objects.select_for_update().get(pk=initial.quote_id)
    quotation = QuoteRevision.objects.select_for_update().select_related("quote", "survey_revision", "package_version").get(pk=pk)
    request_hash = request_fingerprint(action, pk, data)
    previous_request = QuoteRequest.objects.filter(actor=actor, key=data["idempotency_key"]).first()
    if previous_request:
        if previous_request.payload_hash != request_hash:
            raise Conflict("This idempotency key was used for another action.")
        return previous_request.quotation
    check_revision(quotation, data)
    if action == "issue":
        issue_quote(quotation, actor)
    elif action == "accept":
        accept_quote(quotation, data, actor)
    elif action == "reject":
        if quotation.status != QuoteStatus.ISSUED or quotation.valid_until < business_date():
            raise ValidationError({"status": ["Only a current Issued quotation can be rejected."]})
        if not data.get("reason", "").strip():
            raise ValidationError({"reason": ["Record the customer's rejection reason."]})
        transition(quotation, QuoteStatus.REJECTED, actor, reason=data["reason"])
    else:
        raise ValidationError({"action": ["Unknown quotation action."]})
    QuoteRequest.objects.create(actor=actor, key=data["idempotency_key"], payload_hash=request_hash, quotation=quotation)
    return quotation


def issue_quote(quotation, actor):
    if quotation.status != QuoteStatus.DRAFT:
        raise ValidationError({"status": ["Only a Draft quotation can be issued."]})
    Survey.objects.select_for_update().get(pk=quotation.survey_revision.survey_id)
    quotation.survey_revision.refresh_from_db()
    if quotation.survey_revision.status != RevisionStatus.APPROVED:
        raise ValidationError({"survey": ["The source survey was superseded. Review the new approval and generate a fresh quotation."]})
    # A newly reviewed package does not rewrite this draft, but retired/unreviewed sources cannot be issued.
    quotation.package_version.refresh_from_db()
    require_reviewed_package(quotation.package_version)
    previous = quotation.quote.revisions.filter(status=QuoteStatus.ISSUED).exclude(pk=quotation.pk)
    for older in previous:
        transition(older, QuoteStatus.SUPERSEDED, actor, reason="A revised quotation was issued; fresh acceptance is required.")
    quotation.issued_at = timezone.now()
    quotation.issued_by = actor
    quotation.valid_until = business_date() + timedelta(days=quotation.validity_days)
    quotation.content_hash = content_hash(document_content(quotation))
    transition(quotation, QuoteStatus.ISSUED, actor, extras={
        "issued_at": quotation.issued_at, "issued_by": actor, "valid_until": quotation.valid_until,
        "content_hash": quotation.content_hash,
    })


def request_fingerprint(action, pk, data):
    """
    Identifies a retry by the values the caller decided.

    An uploaded file is skipped: two uploads of the same signature are
    different objects, so hashing one would make every retry look new.
    """
    decided = {key: value for key, value in data.items()
               if isinstance(value, (str, int, float, bool, type(None)))}
    return content_hash({"action": action, "pk": pk, **decided})


def accept_quote(quotation, data, actor):
    """
    Records the customer's signature and takes the quotation to Accepted.

    Only a currently valid issued quotation can be signed, and the stored
    document must still hash to what was issued: the customer signs what
    is on the screen, so if the document moved underneath, the signature
    would be evidence of nothing.
    """
    if quotation.status != QuoteStatus.ISSUED or quotation.valid_until < business_date():
        raise ValidationError({"status": ["Only a current Issued quotation can be accepted."]})

    if content_hash(document_content(quotation)) != quotation.content_hash:
        raise ValidationError({"document": [
            "This quotation no longer matches the document that was issued."]})

    Acceptance.objects.create(
        quotation=quotation,
        channel=AcceptanceChannel.SUPERVISED,
        customer_name=data["customer_name"],
        signature=data["signature"],
        document_content_hash=quotation.content_hash,
        witnessed_by=actor,
        accepted_at=timezone.now(),
    )
    transition(quotation, QuoteStatus.ACCEPTED, actor,
               reason=f"Accepted by {data['customer_name']}.")


def transition(quotation, status, actor, *, reason="", extras=None):
    before = {"status": quotation.status, "revision": quotation.revision}
    fields = {"status": status, "revision": quotation.revision + 1, "updated_at": timezone.now(), **(extras or {})}
    QuoteRevision.objects.filter(pk=quotation.pk).update(**fields)
    quotation.refresh_from_db()
    record_event(quotation, status, actor, before=before,
                 after={"status": status, "revision": quotation.revision}, reason=reason)


@transaction.atomic
def expire_quotes():
    """Scheduled command records expiry once; actions also check the date independently."""
    count = 0
    quotes = QuoteRevision.objects.select_for_update().filter(status=QuoteStatus.ISSUED, valid_until__lt=business_date())
    for quotation in quotes:
        transition(quotation, QuoteStatus.EXPIRED, None, reason="Quotation validity ended.")
        count += 1
    return count
