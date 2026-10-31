"""
API contracts for F12. All read-only: warranties come from events.

Acquisition cost is deliberately absent. Every role that can look up a
warranty would otherwise see a figure rules.md section 4 restricts.
"""

from rest_framework import serializers

from apps.inventory.models import SerializedUnit

from .models import AssetWarranty, WarrantyStatus
from .services import replacement_history


class WarrantyFilterSerializer(serializers.Serializer):
    """A bad filter is refused by name rather than ignored or raised as a 500."""

    status = serializers.ChoiceField(choices=WarrantyStatus.choices, required=False)
    order = serializers.IntegerField(min_value=1, required=False)
    customer = serializers.IntegerField(min_value=1, required=False)


class WarrantySerializer(serializers.ModelSerializer):
    asset_id = serializers.CharField(source="unit.asset_id", read_only=True)
    serial_number = serializers.CharField(source="unit.serial_number", read_only=True)
    sku = serializers.CharField(source="unit.product.sku", read_only=True)
    product_name = serializers.CharField(source="unit.product.name", read_only=True)
    unit_status = serializers.CharField(source="unit.status", read_only=True)
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    site_address = serializers.CharField(source="site", read_only=True)
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    status = serializers.CharField(read_only=True)
    last_covered_on = serializers.DateField(read_only=True)
    replaced_by = serializers.IntegerField(
        source="replaced_by.pk", read_only=True, default=None
    )

    class Meta:
        model = AssetWarranty
        fields = ["id", "unit", "asset_id", "serial_number", "sku", "product_name",
                  "unit_status", "customer", "customer_name", "site", "site_address",
                  "order", "order_reference", "delivered_at", "policy_name",
                  "policy_version", "duration_months", "coverage_basis",
                  "coverage_start", "coverage_expires_on", "last_covered_on",
                  "status", "replaces", "replaced_by"]


class HistoryEntrySerializer(WarrantySerializer):
    class Meta(WarrantySerializer.Meta):
        fields = ["id", "asset_id", "serial_number", "sku", "product_name",
                  "delivered_at", "coverage_basis", "coverage_start",
                  "coverage_expires_on", "last_covered_on", "status",
                  "replacement_reason"]


class WarrantyDetailSerializer(WarrantySerializer):
    history = serializers.SerializerMethodField()

    class Meta(WarrantySerializer.Meta):
        fields = [*WarrantySerializer.Meta.fields, "conditions",
                  "fresh_period_on_replacement", "replacement_reason", "history"]

    def get_history(self, warranty):
        return HistoryEntrySerializer(replacement_history(warranty), many=True).data


class UncoveredUnitSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    product_name = serializers.CharField(source="product.name", read_only=True)

    class Meta:
        model = SerializedUnit
        fields = ["id", "asset_id", "serial_number", "sku", "product_name"]
