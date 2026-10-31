"""API contracts for F08."""

from decimal import Decimal

from rest_framework import serializers

from .models import (BatchLot, GoodsReceipt, PurchaseOrder, PurchaseOrderLine,
                     SerializedUnit, StockMovement, Supplier)

SMALLEST_QUANTITY = Decimal("0.01")


# ============================================================
# Supplier and purchasing
# ============================================================

class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ["id", "name", "contact_name", "phone", "email", "gstin",
                  "is_active", "created_at"]
        read_only_fields = ["created_at"]


class PurchaseLineInputSerializer(serializers.Serializer):
    product = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=SMALLEST_QUANTITY
    )
    unit_cost = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal("0"))


class PurchaseOrderCreateSerializer(serializers.Serializer):
    supplier = serializers.IntegerField(min_value=1)
    expected_on = serializers.DateField(required=False, allow_null=True)
    supplier_invoice_reference = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )
    supplier_invoice_amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, required=False, allow_null=True
    )
    lines = PurchaseLineInputSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("A purchase order needs at least one line.")
        products = [line["product"] for line in value]
        if len(products) != len(set(products)):
            raise serializers.ValidationError(
                "List each product once and total the quantity."
            )
        return value


class PurchaseLineSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    unit = serializers.CharField(source="product.unit", read_only=True)
    tracking_method = serializers.CharField(source="product.tracking_method", read_only=True)
    outstanding_quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, read_only=True
    )

    class Meta:
        model = PurchaseOrderLine
        fields = ["id", "product", "sku", "name", "unit", "tracking_method",
                  "quantity", "received_quantity", "outstanding_quantity", "unit_cost"]


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source="supplier.name", read_only=True)
    lines = PurchaseLineSerializer(many=True, read_only=True)

    class Meta:
        model = PurchaseOrder
        fields = ["id", "reference", "supplier", "supplier_name", "status",
                  "supplier_invoice_reference", "supplier_invoice_amount",
                  "supplier_payment_status", "placed_on", "expected_on",
                  "revision", "created_at", "lines"]


# ============================================================
# Receiving
# ============================================================

class ReceiptLineSerializer(serializers.Serializer):
    """
    One purchase order line being booked in.

    Serialized products send serial_numbers; bulk products send batch_id
    and quantity. Sending the wrong pair is refused in the service, where
    the product's tracking method is known.
    """

    line = serializers.IntegerField(min_value=1)
    serial_numbers = serializers.ListField(
        child=serializers.CharField(max_length=100, allow_blank=True), required=False
    )
    batch_id = serializers.CharField(max_length=100, required=False, allow_blank=True)
    quantity = serializers.DecimalField(
        max_digits=12, decimal_places=2, required=False, allow_null=True
    )


class ReceiveSerializer(serializers.Serializer):
    received_on = serializers.DateField()
    delivery_note_reference = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )
    notes = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    lines = ReceiptLineSerializer(many=True)

    def validate_lines(self, value):
        if not value:
            raise serializers.ValidationError("Record at least one line that arrived.")
        return value


class GoodsReceiptSerializer(serializers.ModelSerializer):
    purchase_reference = serializers.CharField(
        source="purchase_order.reference", read_only=True
    )

    class Meta:
        model = GoodsReceipt
        fields = ["id", "reference", "purchase_order", "purchase_reference",
                  "delivery_note_reference", "received_on", "recorded_at", "notes"]


# ============================================================
# Stock
# ============================================================

class SerializedUnitSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    on_hand = serializers.BooleanField(read_only=True)

    class Meta:
        model = SerializedUnit
        fields = ["id", "asset_id", "serial_number", "product", "sku", "name",
                  "status", "on_hand", "location", "acquisition_cost",
                  "goods_receipt", "order", "customer", "site", "created_at"]


class BatchLotSerializer(serializers.ModelSerializer):
    sku = serializers.CharField(source="product.sku", read_only=True)
    name = serializers.CharField(source="product.name", read_only=True)
    on_hand = serializers.BooleanField(read_only=True)

    class Meta:
        model = BatchLot
        fields = ["id", "batch_id", "product", "sku", "name", "quantity", "unit",
                  "status", "on_hand", "location", "unit_cost", "goods_receipt",
                  "order", "created_at"]


class StockMovementSerializer(serializers.ModelSerializer):
    moved_by_name = serializers.CharField(
        source="moved_by.get_full_name", read_only=True, default=""
    )
    asset_id = serializers.CharField(source="unit.asset_id", read_only=True, default="")
    batch_id = serializers.CharField(source="lot.batch_id", read_only=True, default="")

    class Meta:
        model = StockMovement
        fields = ["id", "unit", "asset_id", "lot", "batch_id", "reason", "from_status",
                  "to_status", "quantity", "order", "note", "moved_by",
                  "moved_by_name", "moved_at"]
