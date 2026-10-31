"""
Turning enquiry JSON into Customer, Site and Enquiry records.

The public form sends one flat payload. This file splits it into the
three records and creates them in a single transaction, so a half-saved
enquiry is impossible.
"""

from django.db import transaction
from rest_framework import serializers

from .models import (
    ALLOWED_STATUS_CHANGES,
    ContactChannel,
    ContactLog,
    Customer,
    CustomerType,
    Enquiry,
    EnquirySource,
    EnquiryStatus,
    Site,
    SystemType,
    normalized_address,
)
from .constants import INDIAN_STATES, NATIONAL_PHONE_DIGITS
from apps.uploads import validate_upload


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

    owner_name = serializers.SerializerMethodField()
    duplicate_candidate = CustomerSerializer(source="possible_duplicate_of", read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)
    has_electricity_bill = serializers.SerializerMethodField()
    next_statuses = serializers.SerializerMethodField()

    class Meta:
        model = Enquiry
        fields = [
            "id", "reference", "site", "source", "status",
            "requested_system_type", "requested_capacity_kw",
            "electricity_connection_number",
            "monthly_consumption_kwh", "monthly_bill_amount",
            "billing_period_start", "billing_period_end",
            "has_electricity_bill", "notes",
            "is_possible_duplicate", "created_at",
            # follow-up (F02)
            "owner", "owner_name", "next_action", "next_action_due",
            "is_overdue", "lost_reason", "next_statuses",
            "revision", "qualification_checks", "qualification_reason",
            "possible_duplicate_of", "duplicate_review", "duplicate_review_reason",
            "duplicate_candidate",
        ]

    def get_is_possible_duplicate(self, enquiry) -> bool:
        return enquiry.possible_duplicate_of_id is not None and not enquiry.duplicate_review

    def get_owner_name(self, enquiry):
        return (enquiry.owner.get_full_name() or enquiry.owner.username) if enquiry.owner else ""

    def get_has_electricity_bill(self, enquiry) -> bool:
        return bool(enquiry.electricity_bill)

    def get_next_statuses(self, enquiry) -> list:
        """The moves open from here, so a screen never repeats the rules."""
        return list(ALLOWED_STATUS_CHANGES.get(enquiry.status, []))


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

        if len(digits) > NATIONAL_PHONE_DIGITS:
            digits = digits[-NATIONAL_PHONE_DIGITS:]

        if len(digits) != NATIONAL_PHONE_DIGITS:
            raise serializers.ValidationError(
                "Enter a 10-digit phone number."
            )
        return digits

    def validate_electricity_bill(self, value):
        """This field is open to the public, so nothing is taken on trust."""
        return validate_upload(value) if value else value

    def validate(self, data):
        for field in ("shadow_free_roof_area_sqm", "requested_capacity_kw",
                      "monthly_consumption_kwh", "monthly_bill_amount"):
            if data.get(field) is not None and data[field] < 0:
                raise serializers.ValidationError({field: "Enter a non-negative value."})
        start = data.get("billing_period_start")
        end = data.get("billing_period_end")
        if data.get("monthly_bill_amount") is not None or start or end:
            missing = {}
            if not start:
                missing["billing_period_start"] = "Enter the start of the bill's billing period."
            if not end:
                missing["billing_period_end"] = "Enter the end of the bill's billing period."
            if missing:
                raise serializers.ValidationError(missing)
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
        if existing_customer is None:
            matching_site = Site.objects.filter(address_key=normalized_address(
                site_data["address_line"], site_data["city"], site_data["state"], site_data["pincode"]
            )).select_related("customer").order_by("id").first()
            existing_customer = matching_site.customer if matching_site else None

        customer = Customer.objects.create(**customer_data)
        site = Site.objects.create(customer=customer, **site_data)

        enquiry = Enquiry.objects.create(
            site=site,
            possible_duplicate_of=existing_customer,
            **validated_data,
        )
        # Public intake has an explicit next action even before a salesperson picks it up.
        from apps.core.api import business_date
        from apps.core.models import record_event
        enquiry.next_action = "Assign a sales owner and contact the customer"
        enquiry.next_action_due = business_date()
        enquiry.save(update_fields=["next_action", "next_action_due"])
        record_event(enquiry, "received", after={"source": enquiry.source})
        return enquiry


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
    revision = serializers.IntegerField(min_value=1)
    next_action = serializers.CharField(max_length=200)
    next_action_due = serializers.DateField()


class EnquiryStatusChangeSerializer(serializers.Serializer):
    """
    Requests a move to a new status.

    The model decides whether the move is legal and what each target
    requires; this only checks the shape of the request.
    """

    status = serializers.ChoiceField(choices=EnquiryStatus.choices)
    revision = serializers.IntegerField(min_value=1)
    qualification_checks = serializers.DictField(child=serializers.BooleanField(), required=False)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    next_action = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    next_action_due = serializers.DateField(required=False, allow_null=True)
