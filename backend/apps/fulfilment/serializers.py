"""API contracts for F09."""

from decimal import Decimal

from rest_framework import serializers

from .models import Fulfilment, PackingLine, ScanEvent

SMALLEST_QUANTITY = Decimal("0.01")


# ============================================================
# Inputs
# ============================================================

class RevisionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)


class ScanSerializer(serializers.Serializer):
    """
    One scan. The code is a serial, an asset id or a batch id.

    Which it is decides itself from what the code matches, so the
    scanner can be pointed at anything in the box without the operator
    first telling the screen what kind of thing it is.
    """

    code = serializers.CharField(max_length=100)
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True,
        min_value=SMALLEST_QUANTITY,
    )
    entered_manually = serializers.BooleanField(default=False)
    manual_reason = serializers.CharField(
        max_length=3000, required=False, allow_blank=True
    )


class DispatchSerializer(RevisionSerializer):
    carrier_reference = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )


class DeliverSerializer(RevisionSerializer):
    delivered_at = serializers.DateTimeField()
    received_by_name = serializers.CharField(max_length=150)
    delivery_notes = serializers.CharField(
        max_length=3000, required=False, allow_blank=True
    )


# ============================================================
# Outputs
# ============================================================

class ScanEventSerializer(serializers.ModelSerializer):
    asset_id = serializers.CharField(source="unit.asset_id", read_only=True, default="")
    serial_number = serializers.CharField(
        source="unit.serial_number", read_only=True, default=""
    )
    batch_id = serializers.CharField(source="lot.batch_id", read_only=True, default="")
    scanned_by_name = serializers.CharField(
        source="scanned_by.get_full_name", read_only=True, default=""
    )

    class Meta:
        model = ScanEvent
        fields = ["id", "unit", "asset_id", "serial_number", "lot", "batch_id",
                  "quantity", "entered_manually", "manual_reason",
                  "scanned_by", "scanned_by_name", "scanned_at"]


class PackingLineSerializer(serializers.ModelSerializer):
    scans = ScanEventSerializer(many=True, read_only=True)
    outstanding_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )
    is_complete = serializers.BooleanField(read_only=True)

    class Meta:
        model = PackingLine
        fields = ["id", "product", "sku", "description", "unit", "tracking_method",
                  "required_quantity", "reserved_quantity", "packed_quantity",
                  "outstanding_quantity", "is_complete", "scans"]


class FulfilmentSerializer(serializers.ModelSerializer):
    order_reference = serializers.CharField(source="order.reference", read_only=True)
    customer_name = serializers.CharField(
        source="order.customer.full_name", read_only=True
    )
    lines = PackingLineSerializer(many=True, read_only=True)
    is_complete = serializers.BooleanField(read_only=True)
    dispatch_allowed = serializers.SerializerMethodField()

    class Meta:
        model = Fulfilment
        fields = ["id", "order", "order_reference", "customer_name", "status",
                  "blocked_reason", "is_complete", "dispatch_allowed",
                  "carrier_reference", "dispatched_at", "delivered_at",
                  "delivery_recorded_at", "received_by_name", "delivery_notes",
                  "revision", "created_at", "lines"]

    def get_dispatch_allowed(self, fulfilment):
        """Both gates, so the warehouse screen can say which one is shut."""
        return fulfilment.status == "packed" and fulfilment.order.dispatch_allowed
