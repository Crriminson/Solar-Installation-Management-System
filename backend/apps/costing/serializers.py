"""
API contracts for F14.

A technician may record their own hours, but rates and amounts are
restricted labour cost, so TimeEntrySerializer drops them for anyone
without cost access.
"""

from decimal import Decimal

from rest_framework import serializers

from apps.catalogue.permissions import can_view_costs

from .models import (ProjectExpense, SupplierPayment, TechnicianPayment, TechnicianRate,
                     TimeEntry)

SMALLEST_AMOUNT = Decimal("0.01")


# ============================================================
# Inputs
# ============================================================

class ReverseSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=3000)


class RateInputSerializer(serializers.Serializer):
    technician = serializers.IntegerField(min_value=1)
    rate_per_hour = serializers.DecimalField(
        max_digits=10, decimal_places=2, min_value=SMALLEST_AMOUNT
    )
    effective_from = serializers.DateField()


class TimeInputSerializer(serializers.Serializer):
    job = serializers.IntegerField(min_value=1)
    technician = serializers.IntegerField(min_value=1, required=False)
    work_date = serializers.DateField()
    hours = serializers.DecimalField(
        max_digits=5, decimal_places=2, min_value=SMALLEST_AMOUNT, max_value=Decimal("24")
    )
    note = serializers.CharField(max_length=300, required=False, allow_blank=True)


class TechnicianPaymentInputSerializer(serializers.Serializer):
    technician = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=SMALLEST_AMOUNT)
    paid_on = serializers.DateField()
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)


class ExpenseInputSerializer(serializers.Serializer):
    order = serializers.IntegerField(min_value=1)
    description = serializers.CharField(max_length=250)
    amount_excl_tax = serializers.DecimalField(
        max_digits=12, decimal_places=2, min_value=SMALLEST_AMOUNT
    )
    incurred_on = serializers.DateField()


class SupplierInvoiceInputSerializer(serializers.Serializer):
    reference = serializers.CharField(max_length=100)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=Decimal("0"))


class SupplierPaymentInputSerializer(serializers.Serializer):
    purchase_order = serializers.IntegerField(min_value=1)
    amount = serializers.DecimalField(max_digits=14, decimal_places=2, min_value=SMALLEST_AMOUNT)
    paid_on = serializers.DateField()
    reference = serializers.CharField(max_length=100, required=False, allow_blank=True)


# ============================================================
# Outputs
# ============================================================

class RateSerializer(serializers.ModelSerializer):
    technician_name = serializers.CharField(source="technician", read_only=True)

    class Meta:
        model = TechnicianRate
        fields = ["id", "technician", "technician_name", "rate_per_hour", "effective_from",
                  "created_at"]


class TimeEntrySerializer(serializers.ModelSerializer):
    technician_name = serializers.CharField(source="technician", read_only=True)
    is_reversed = serializers.BooleanField(read_only=True)

    class Meta:
        model = TimeEntry
        fields = ["id", "job", "technician", "technician_name", "work_date", "hours",
                  "rate_per_hour", "cost_amount", "note", "is_reversed", "reversed_reason",
                  "recorded_at"]

    def to_representation(self, entry):
        data = super().to_representation(entry)
        if not can_view_costs(self.context["request"].user):
            data.pop("rate_per_hour")
            data.pop("cost_amount")
        return data


class TechnicianPaymentSerializer(serializers.ModelSerializer):
    technician_name = serializers.CharField(source="technician", read_only=True)
    is_reversed = serializers.BooleanField(read_only=True)

    class Meta:
        model = TechnicianPayment
        fields = ["id", "technician", "technician_name", "amount", "paid_on", "reference",
                  "is_reversed", "reversed_reason", "recorded_at"]


class ExpenseSerializer(serializers.ModelSerializer):
    is_reversed = serializers.BooleanField(read_only=True)

    class Meta:
        model = ProjectExpense
        fields = ["id", "order", "description", "amount_excl_tax", "incurred_on",
                  "is_reversed", "reversed_reason", "recorded_at"]


class SupplierPaymentSerializer(serializers.ModelSerializer):
    purchase_reference = serializers.CharField(source="purchase_order.reference", read_only=True)
    is_reversed = serializers.BooleanField(read_only=True)

    class Meta:
        model = SupplierPayment
        fields = ["id", "purchase_order", "purchase_reference", "amount", "paid_on", "reference",
                  "is_reversed", "reversed_reason", "recorded_at"]
