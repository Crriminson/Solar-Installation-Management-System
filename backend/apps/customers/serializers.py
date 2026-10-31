"""
Turning enquiry JSON into Customer, Site and Enquiry records.

The public form sends one flat payload. This file splits it into the
three records and creates them in a single transaction, so a half-saved
enquiry is impossible.
"""

from django.db import transaction
from rest_framework import serializers

from .models import (
    ContactChannel,
    ContactLog,
    Customer,
    CustomerType,
    Enquiry,
    EnquirySource,
    EnquiryStatus,
    Site,
    SystemType,
)
from .constants import INDIAN_STATES


# ============================================================
# Reading
# ============================================================

class CustomerSerializer(serializers.ModelSerializer):
    class Meta:
        model = Customer
        fields = ["id", "full_name", "phone", "email", "customer_type"]


class SiteSerializer(serializers.ModelSerializer):
    customer = CustomerSerializer(read_only=True)

    class Meta:
        model = Site
        fields = [
            "id", "customer", "address_line", "city", "state", "pincode",
            "shadow_free_roof_area_sqm",
        ]


class EnquiryListSerializer(serializers.ModelSerializer):
    """What the sales queue shows for each enquiry."""

    site = SiteSerializer(read_only=True)
    is_possible_duplicate = serializers.SerializerMethodField()

    owner_name = serializers.CharField(
        source="owner.get_full_name", default="", read_only=True
    )
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Enquiry
        fields = [
            "id", "reference", "site", "source", "status",
            "requested_system_type", "requested_capacity_kw",
            "monthly_consumption_kwh", "monthly_bill_amount",
            "is_possible_duplicate", "created_at",
            # follow-up (F02)
            "owner", "owner_name", "next_action", "next_action_due",
            "is_overdue", "lost_reason",
        ]

    def get_is_possible_duplicate(self, enquiry) -> bool:
        return enquiry.possible_duplicate_of_id is not None


# ============================================================
# Writing
# ============================================================

class EnquiryCreateSerializer(serializers.Serializer):
    """
    One flat payload from the enquiry form.

    Only the fields needed to contact the customer and find the roof are
    required. Everything about electricity usage is optional, because a
    caller often does not have their bill to hand and we would rather
    capture the enquiry than lose it over a missing number.
    """

    # Customer
    full_name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, allow_blank=True)
    customer_type = serializers.ChoiceField(
        choices=CustomerType.choices, default=CustomerType.RESIDENTIAL
    )

    # Site
    address_line = serializers.CharField(max_length=255)
    city = serializers.CharField(max_length=100)
    state = serializers.ChoiceField(choices=INDIAN_STATES)
    pincode = serializers.CharField(max_length=10)
    shadow_free_roof_area_sqm = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True
    )

    # Enquiry
    source = serializers.ChoiceField(
        choices=EnquirySource.choices, default=EnquirySource.WEB_FORM
    )
    requested_system_type = serializers.ChoiceField(
        choices=SystemType.choices, default=SystemType.UNDECIDED
    )
    requested_capacity_kw = serializers.DecimalField(
        max_digits=5, decimal_places=2, required=False, allow_null=True
    )
    electricity_connection_number = serializers.CharField(
        max_length=50, required=False, allow_blank=True
    )
    monthly_consumption_kwh = serializers.DecimalField(
        max_digits=8, decimal_places=2, required=False, allow_null=True
    )
    monthly_bill_amount = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    billing_period_start = serializers.DateField(required=False, allow_null=True)
    billing_period_end = serializers.DateField(required=False, allow_null=True)
    electricity_bill = serializers.FileField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)

    def validate_phone(self, value):
        """
        Stores every phone number the same way, as 10 national digits.

        The same person writes their number as 9876543210, +91 98765
        43210 or 09876543210. Duplicate detection compares these as
        strings, so they have to normalise to one form or a repeat
        caller is never flagged. Indian mobile numbers are 10 digits,
        so anything longer is a country code or trunk prefix and the
        last 10 digits are the number.
        """
        digits = "".join(character for character in value if character.isdigit())

        if len(digits) > 10:
            digits = digits[-10:]

        if len(digits) != 10:
            raise serializers.ValidationError(
                "Enter a 10-digit phone number."
            )
        return digits

    def validate(self, data):
        start = data.get("billing_period_start")
        end = data.get("billing_period_end")
        if start and end and end < start:
            raise serializers.ValidationError(
                {"billing_period_end": "Billing period cannot end before it starts."}
            )
        return data

    @transaction.atomic
    def create(self, validated_data):
        """
        Creates the customer, site and enquiry together.

        Wrapped in a transaction so the caller is never told an enquiry
        succeeded when only part of it was written.
        """
        customer_fields = ["full_name", "phone", "email", "customer_type"]
        site_fields = [
            "address_line", "city", "state", "pincode",
            "shadow_free_roof_area_sqm",
        ]

        customer_data = {
            key: validated_data.pop(key)
            for key in customer_fields
            if key in validated_data
        }
        site_data = {
            key: validated_data.pop(key)
            for key in site_fields
            if key in validated_data
        }

        # Flag an existing customer with the same phone, but still save
        # this enquiry as its own record. A human decides if they match.
        existing_customer = Customer.objects.filter(
            phone=customer_data["phone"]
        ).first()

        customer = Customer.objects.create(**customer_data)
        site = Site.objects.create(customer=customer, **site_data)

        return Enquiry.objects.create(
            site=site,
            possible_duplicate_of=existing_customer,
            **validated_data,
        )


# ============================================================
# Follow-up (F02)
# ============================================================

class ContactLogSerializer(serializers.ModelSerializer):
    """A recorded contact attempt. The staff member comes from session."""

    staff_name = serializers.CharField(
        source="staff.get_full_name", default="", read_only=True
    )

    class Meta:
        model = ContactLog
        fields = [
            "id", "enquiry", "staff", "staff_name", "channel",
            "contacted_at", "summary", "reached_customer", "created_at",
        ]
        # enquiry comes from the URL and staff from the session, so
        # neither is accepted from the request body.
        read_only_fields = ["enquiry", "staff", "created_at"]

    def validate_contacted_at(self, value):
        """A contact cannot have happened in the future."""
        from django.utils import timezone

        if value > timezone.now():
            raise serializers.ValidationError(
                "A contact cannot be recorded in the future."
            )
        return value


class EnquiryAssignSerializer(serializers.Serializer):
    """Hands an enquiry to a named owner."""

    owner = serializers.IntegerField()
    next_action = serializers.CharField(max_length=200)
    next_action_due = serializers.DateField(required=False, allow_null=True)


class EnquiryStatusChangeSerializer(serializers.Serializer):
    """
    Requests a move to a new status.

    The model decides whether the move is legal and what each target
    requires; this only checks the shape of the request.
    """

    status = serializers.ChoiceField(choices=EnquiryStatus.choices)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    next_action = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    next_action_due = serializers.DateField(required=False, allow_null=True)
