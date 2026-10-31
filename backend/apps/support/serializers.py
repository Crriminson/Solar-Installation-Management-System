"""
API contracts for F13.

Internal cost is removed from responses unless the viewer may see it,
the same way the catalogue hides purchase cost from Sales (D039).
"""

from decimal import Decimal

from rest_framework import serializers

from apps.catalogue.permissions import can_view_costs
from apps.scheduling.models import Job
from apps.uploads import validate_image

from .models import (Assessment, Disposition, EstimateLine, Priority, RepairEstimate,
                     Replacement, ServiceTicket, TicketAsset, TicketPhoto, TicketStatus, WorkLine)
from .services import is_office

SMALLEST_QUANTITY = Decimal("0.01")

# What the server says can happen next, so buttons never copy its rules.
NEXT_ACTIONS = {
    TicketStatus.NEW: ["visit", "diagnose", "review"],
    TicketStatus.DIAGNOSED: ["estimate", "decide-estimate", "review", "start-work"],
    TicketStatus.IN_PROGRESS: ["work-line", "void-line", "replace", "estimate",
                               "decide-estimate", "visit", "finish"],
    TicketStatus.AWAITING_CONFIRMATION: ["confirm", "send-back"],
    TicketStatus.CLOSED: ["reopen"],
}


# ============================================================
# Inputs
# ============================================================

class RevisionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=3000, required=False, allow_blank=True)


class RaiseSerializer(serializers.Serializer):
    customer = serializers.IntegerField(min_value=1)
    units = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)
    fault_description = serializers.CharField(max_length=3000)
    fault_code = serializers.CharField(max_length=50, required=False, allow_blank=True)
    priority = serializers.ChoiceField(choices=Priority.choices, required=False)
    claimed_complaint_at = serializers.DateTimeField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(max_length=80, required=False, allow_blank=True)


class AssignSerializer(RevisionSerializer):
    owner = serializers.IntegerField(min_value=1)


class BlockSerializer(RevisionSerializer):
    owner = serializers.IntegerField(min_value=1)


class ReviewSerializer(RevisionSerializer):
    asset = serializers.IntegerField(min_value=1)
    assessment = serializers.ChoiceField(
        choices=[Assessment.COVERED, Assessment.NOT_COVERED]
    )


class VisitSerializer(serializers.Serializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    notes = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    technicians = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )


class DiagnoseSerializer(RevisionSerializer):
    job = serializers.IntegerField(min_value=1)
    findings = serializers.CharField(max_length=5000)
    recommendation = serializers.CharField(max_length=5000)


class EstimateLineInputSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=SMALLEST_QUANTITY
    )


class EstimateSerializer(RevisionSerializer):
    lines = EstimateLineInputSerializer(many=True, allow_empty=False)


class DecideEstimateSerializer(RevisionSerializer):
    approved = serializers.BooleanField()
    customer_name = serializers.CharField(max_length=150)


class WorkLineInputSerializer(serializers.Serializer):
    asset = serializers.IntegerField(min_value=1)
    product = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=SMALLEST_QUANTITY
    )


class VoidLineSerializer(serializers.Serializer):
    line = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=3000)


class ReplaceSerializer(serializers.Serializer):
    asset = serializers.IntegerField(min_value=1)
    code = serializers.CharField(max_length=100)
    disposition = serializers.ChoiceField(choices=Disposition.choices)
    reason = serializers.CharField(max_length=3000)


class ConfirmSerializer(RevisionSerializer):
    customer_name = serializers.CharField(max_length=150)


class PhotoInputSerializer(serializers.Serializer):
    image = serializers.ImageField(validators=[validate_image])
    caption = serializers.CharField(max_length=200)


# ============================================================
# Outputs
# ============================================================

class TicketAssetSerializer(serializers.ModelSerializer):
    asset_id = serializers.CharField(source="unit.asset_id", read_only=True)
    serial_number = serializers.CharField(source="unit.serial_number", read_only=True)
    sku = serializers.CharField(source="unit.product.sku", read_only=True)
    product_name = serializers.CharField(source="unit.product.name", read_only=True)
    last_covered_on = serializers.DateField(
        source="warranty.last_covered_on", read_only=True, default=None
    )
    policy_name = serializers.CharField(source="warranty.policy_name", read_only=True, default="")
    replaced = serializers.SerializerMethodField()

    class Meta:
        model = TicketAsset
        fields = ["id", "unit", "asset_id", "serial_number", "sku", "product_name",
                  "warranty", "policy_name", "last_covered_on", "assessment",
                  "review_reason", "reviewed_at", "replaced"]

    def get_replaced(self, asset):
        return hasattr(asset, "replacement")


class EstimateLineSerializer(serializers.ModelSerializer):
    class Meta:
        model = EstimateLine
        fields = ["id", "sku", "description", "unit", "quantity", "unit_price_excl_tax",
                  "gst_rate_percent", "net_excl_tax", "tax_amount"]


class RepairEstimateSerializer(serializers.ModelSerializer):
    lines = EstimateLineSerializer(many=True, read_only=True)

    class Meta:
        model = RepairEstimate
        fields = ["id", "number", "status", "net_excl_tax", "tax_amount", "gross_incl_tax",
                  "decided_by_name", "decided_at", "created_at", "lines"]


class WorkLineSerializer(serializers.ModelSerializer):
    invoice_reference = serializers.CharField(
        source="invoice.reference", read_only=True, default=""
    )

    class Meta:
        model = WorkLine
        fields = ["id", "asset", "sku", "description", "unit", "quantity", "charge_excl_tax",
                  "charge_tax", "unit_cost", "invoice", "invoice_reference",
                  "voided_reason", "recorded_at"]


class ReplacementSerializer(serializers.ModelSerializer):
    old_asset_id = serializers.CharField(source="old_unit.asset_id", read_only=True)
    new_asset_id = serializers.CharField(source="new_unit.asset_id", read_only=True)

    class Meta:
        model = Replacement
        fields = ["id", "asset", "old_unit", "old_asset_id", "new_unit", "new_asset_id",
                  "disposition", "new_warranty", "reason", "replaced_at"]


class TicketPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = TicketPhoto
        fields = ["id", "caption", "uploaded_at"]


class VisitReadSerializer(serializers.ModelSerializer):
    technicians = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = ["id", "status", "starts_at", "ends_at", "technicians"]

    def get_technicians(self, job):
        return [str(assignment.technician) for assignment in job.assignments.all()]


class TicketListSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    owner_name = serializers.CharField(source="owner", read_only=True, default="")
    is_blocked = serializers.BooleanField(read_only=True)
    covered = serializers.SerializerMethodField()

    class Meta:
        model = ServiceTicket
        fields = ["id", "reference", "status", "priority", "customer", "customer_name",
                  "fault_description", "owner", "owner_name", "is_blocked",
                  "complaint_at", "covered"]

    def get_covered(self, ticket):
        """Covered only when every affected unit is."""
        return all(asset.is_covered for asset in ticket.assets.all())


class TicketDetailSerializer(TicketListSerializer):
    customer_phone = serializers.CharField(source="customer.phone", read_only=True)
    site_address = serializers.CharField(source="site", read_only=True)
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    assets = TicketAssetSerializer(many=True, read_only=True)
    estimates = RepairEstimateSerializer(many=True, read_only=True)
    work_lines = WorkLineSerializer(many=True, read_only=True)
    replacements = ReplacementSerializer(many=True, read_only=True)
    photos = TicketPhotoSerializer(many=True, read_only=True)
    visits = VisitReadSerializer(source="jobs", many=True, read_only=True)
    allowed_actions = serializers.SerializerMethodField()

    class Meta(TicketListSerializer.Meta):
        fields = [*TicketListSerializer.Meta.fields, "customer_phone", "site", "site_address",
                  "order", "order_reference", "fault_code", "claimed_complaint_at",
                  "findings", "recommendation", "diagnosed_at", "blocked_reason",
                  "blocked_owner", "confirmed_by_name", "confirmed_at", "revision",
                  "assets", "estimates", "work_lines", "replacements", "photos",
                  "visits", "allowed_actions"]

    def get_allowed_actions(self, ticket):
        return NEXT_ACTIONS[ticket.status]

    def to_representation(self, ticket):
        """Cost for those allowed it; the customer's number for the office."""
        data = super().to_representation(ticket)
        user = self.context["request"].user

        if not can_view_costs(user):
            for line in data["work_lines"]:
                line.pop("unit_cost")
        if not is_office(user):
            data.pop("customer_phone")
        return data
