"""API contracts for F11."""

from decimal import Decimal

from rest_framework import serializers

from apps.customers.models import SystemType
from apps.uploads import validate_image

from .models import (Decision, InstallationAcceptance, InstallationPhoto,
                     InstallationReport, InstalledUnit, MANDATORY_CHECKS)


# ============================================================
# Inputs
# ============================================================

class ChecklistEntrySerializer(serializers.Serializer):
    item = serializers.CharField(max_length=60)
    passed = serializers.BooleanField()
    note = serializers.CharField(max_length=500, required=False, allow_blank=True)


class ReportUpdateSerializer(serializers.Serializer):
    """Everything the crew fills in. All optional: the form saves as it goes."""

    revision = serializers.IntegerField(min_value=1)
    started_at = serializers.DateTimeField(required=False)
    finished_at = serializers.DateTimeField(required=False)
    system_type = serializers.ChoiceField(
        choices=[(SystemType.ON_GRID.value, SystemType.ON_GRID.label),
                 (SystemType.OFF_GRID.value, SystemType.OFF_GRID.label)],
        required=False,
    )
    installed_capacity_kw = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, min_value=Decimal("0.01")
    )
    checklist = ChecklistEntrySerializer(many=True, required=False)
    generation_test_kw = serializers.DecimalField(
        max_digits=6, decimal_places=2, required=False, allow_null=True
    )
    generation_test_passed = serializers.BooleanField(required=False)
    generation_test_notes = serializers.CharField(
        max_length=3000, required=False, allow_blank=True
    )
    notes = serializers.CharField(max_length=3000, required=False, allow_blank=True)


class InstalledUnitSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=100)
    position_note = serializers.CharField(
        max_length=200, required=False, allow_blank=True
    )


class PhotoSerializer(serializers.Serializer):
    image = serializers.ImageField()
    caption = serializers.CharField(max_length=200)

    def validate_image(self, value):
        return validate_image(value)


class RevisionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)


class DecisionSerializer(serializers.Serializer):
    """
    The customer's answer, against the revision they were shown.

    document_revision is not a formality: it is what stops a signature
    being attached to a report that was corrected after they read it.
    """

    decision = serializers.ChoiceField(choices=Decision.choices)
    document_revision = serializers.IntegerField(min_value=1)
    customer_name = serializers.CharField(max_length=150)
    signature = serializers.ImageField(required=False)
    refusal_reason = serializers.CharField(
        max_length=3000, required=False, allow_blank=True
    )

    def validate_customer_name(self, value):
        if not value.strip():
            raise serializers.ValidationError("The customer types their own name.")
        return value.strip()

    def validate_signature(self, value):
        return validate_image(value)


# ============================================================
# Outputs
# ============================================================

class InstalledUnitReadSerializer(serializers.ModelSerializer):
    asset_id = serializers.CharField(source="unit.asset_id", read_only=True)
    serial_number = serializers.CharField(source="unit.serial_number", read_only=True)
    sku = serializers.CharField(source="unit.product.sku", read_only=True)
    name = serializers.CharField(source="unit.product.name", read_only=True)

    class Meta:
        model = InstalledUnit
        fields = ["id", "unit", "asset_id", "serial_number", "sku", "name",
                  "position_note", "recorded_at"]


class PhotoReadSerializer(serializers.ModelSerializer):
    class Meta:
        model = InstallationPhoto
        fields = ["id", "image", "caption", "uploaded_at"]


class AcceptanceSerializer(serializers.ModelSerializer):
    witnessed_by_name = serializers.CharField(
        source="witnessed_by.get_full_name", read_only=True, default=""
    )

    class Meta:
        model = InstallationAcceptance
        fields = ["id", "decision", "customer_name", "signature", "refusal_reason",
                  "document_revision", "document_content_hash",
                  "witnessed_by", "witnessed_by_name", "decided_at"]


class ReportSerializer(serializers.ModelSerializer):
    installed_units = InstalledUnitReadSerializer(many=True, read_only=True)
    photos = PhotoReadSerializer(many=True, read_only=True)
    acceptance = AcceptanceSerializer(read_only=True)
    missing_evidence = serializers.SerializerMethodField()
    mandatory_checks = serializers.SerializerMethodField()
    customer_name = serializers.CharField(
        source="job.site.customer.full_name", read_only=True
    )

    class Meta:
        model = InstallationReport
        fields = ["id", "job", "customer_name", "status", "started_at", "finished_at",
                  "system_type", "installed_capacity_kw", "checklist",
                  "generation_test_kw", "generation_test_passed",
                  "generation_test_notes", "notes", "content_hash", "submitted_at",
                  "revision", "created_at", "missing_evidence", "mandatory_checks",
                  "installed_units", "photos", "acceptance"]

    def get_missing_evidence(self, report):
        """Shown live on the form, so the crew knows what is left."""
        return report.missing_evidence()

    def get_mandatory_checks(self, report):
        return MANDATORY_CHECKS
