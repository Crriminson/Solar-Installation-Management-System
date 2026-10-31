"""Quotation API contracts: generation inputs contain no handwritten component basket."""

from rest_framework import serializers

from apps.core.api import business_date
from .models import QuoteLine, QuoteRevision, QuoteStatus


class GenerateSerializer(serializers.Serializer):
    enquiry = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=100)
    previous_revision = serializers.IntegerField(min_value=1, required=False)
    revision = serializers.IntegerField(min_value=1, required=False)
    payment_plan = serializers.ChoiceField(choices=["advance", "full"], default="advance")
    advance_percent = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    terms_notes = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    subsidy_facts = serializers.DictField(child=serializers.BooleanField(), required=False)


class ActionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=100)
    reason = serializers.CharField(max_length=3000, required=False, allow_blank=True)


class QuoteLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuoteLine
        fields = ["id", "sku", "description", "unit", "quantity", "unit_price_excl_tax",
                  "gst_rate_percent", "net_excl_tax", "tax_amount", "gross_incl_tax"]


class QuoteSerializer(serializers.ModelSerializer):
    reference = serializers.CharField(source="quote.reference")
    enquiry = serializers.IntegerField(source="quote.enquiry_id")
    lines = QuoteLineSerializer(many=True, read_only=True)
    actions = serializers.SerializerMethodField()
    requires_survey_review = serializers.SerializerMethodField()
    display_status = serializers.SerializerMethodField()

    class Meta:
        model = QuoteRevision
        fields = ["id", "reference", "enquiry", "revision_number", "revision", "status", "display_status",
                  "survey_revision", "package_version", "snapshot", "subsidy", "terms", "lines",
                  "subtotal_excl_tax", "tax_amount", "gross_payable_incl_tax", "valid_until", "validity_days",
                  "created_at", "issued_at", "content_hash", "requires_survey_review", "actions"]

    def get_requires_survey_review(self, quotation):
        return quotation.survey_revision.status != "approved"

    def get_display_status(self, quotation):
        if quotation.status == QuoteStatus.ISSUED and quotation.valid_until < business_date():
            return QuoteStatus.EXPIRED
        return quotation.status

    def get_actions(self, quotation):
        user = self.context["request"].user
        if not user.has_role("sales"):
            return []
        actions = []
        if quotation.status == QuoteStatus.DRAFT and not self.get_requires_survey_review(quotation):
            actions.append("issue")
        if self.get_display_status(quotation) == QuoteStatus.ISSUED:
            actions.append("reject")
        if quotation.status != QuoteStatus.ACCEPTED:
            actions.append("generate_revision")
        return actions
