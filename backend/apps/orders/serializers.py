"""API contracts for F07. Amounts arrive as decimals, never floats."""

from decimal import Decimal

from rest_framework import serializers

from .models import (Allocation, Invoice, Order, Payment, PaymentKind, PaymentMethod,
                     PaymentStatus)

SMALLEST_AMOUNT = Decimal("0.01")


# ============================================================
# Inputs
# ============================================================

class ConfirmSerializer(serializers.Serializer):
    quotation = serializers.IntegerField(min_value=1)


class RevisionSerializer(serializers.Serializer):
    """Every write carries the revision the user had on screen."""

    revision = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=3000, required=False, allow_blank=True)


class PaymentCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=PaymentKind.choices, default=PaymentKind.RECEIPT)
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=SMALLEST_AMOUNT
    )
    method = serializers.ChoiceField(choices=PaymentMethod.choices)
    external_reference = serializers.CharField(
        max_length=100, required=False, allow_blank=True
    )
    status = serializers.ChoiceField(
        choices=[PaymentStatus.PENDING, PaymentStatus.CLEARED],
        default=PaymentStatus.PENDING,
    )
    paid_on = serializers.DateField()


class AllocateSerializer(serializers.Serializer):
    invoice = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(
        max_digits=14, decimal_places=2, min_value=SMALLEST_AMOUNT
    )


# ============================================================
# Outputs
# ============================================================

class AllocationSerializer(serializers.ModelSerializer):
    invoice_reference = serializers.CharField(source="invoice.reference", read_only=True)

    class Meta:
        model = Allocation
        fields = ["id", "invoice", "invoice_reference", "amount", "created_at"]


class InvoiceSerializer(serializers.ModelSerializer):
    settled = serializers.BooleanField(read_only=True)
    outstanding = serializers.SerializerMethodField()

    class Meta:
        model = Invoice
        fields = ["id", "reference", "kind", "amount", "paid_amount", "outstanding",
                  "settled", "issued_at"]

    def get_outstanding(self, invoice):
        return invoice.amount - invoice.paid_amount


class PaymentSerializer(serializers.ModelSerializer):
    recorded_by_name = serializers.CharField(
        source="recorded_by.get_full_name", read_only=True, default=""
    )
    allocations = AllocationSerializer(many=True, read_only=True)
    unallocated = serializers.DecimalField(
        max_digits=14, decimal_places=2, read_only=True
    )

    class Meta:
        model = Payment
        fields = ["id", "kind", "amount", "allocated_amount", "unallocated", "method",
                  "external_reference", "status", "paid_on", "recorded_at",
                  "recorded_by", "recorded_by_name", "reversed_reason", "revision",
                  "allocations"]


class OrderSerializer(serializers.ModelSerializer):
    quotation_reference = serializers.CharField(
        source="quotation.quote.reference", read_only=True
    )
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    invoices = InvoiceSerializer(many=True, read_only=True)
    payments = PaymentSerializer(many=True, read_only=True)

    cleared_total = serializers.SerializerMethodField()
    outstanding = serializers.SerializerMethodField()
    advance_cleared = serializers.BooleanField(read_only=True)
    dispatch_allowed = serializers.BooleanField(read_only=True)

    class Meta:
        model = Order
        fields = ["id", "reference", "status", "quotation", "quotation_reference",
                  "customer", "customer_name", "site", "payment_plan", "gross_payable",
                  "advance_payable", "balance_due_on", "cleared_total", "outstanding",
                  "advance_cleared", "dispatch_allowed", "cancelled_reason",
                  "confirmed_at", "revision", "invoices", "payments"]

    def get_cleared_total(self, order):
        return order.cleared_total()

    def get_outstanding(self, order):
        return order.outstanding()
