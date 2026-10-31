"""
Survey serializers (F03).

Reading a survey shows every revision, because the history of what was
reported and sent back is part of the record. Writing only ever creates
a new revision — nothing edits a reviewed one.
"""

from decimal import Decimal

from django.urls import reverse
from django.utils import timezone
from rest_framework import serializers

from apps.customers.models import SystemType
from apps.uploads import validate_image

from .models import RevisionStatus, Survey, SurveyPhoto, SurveyRevision


# Fields a technician fills in. Listed once and reused, so the create
# form and the read view cannot drift apart.
MEASUREMENT_FIELDS = [
    "roof_type", "roof_length_m", "roof_width_m", "usable_area_sqm",
    "orientation", "tilt_degrees", "shading_notes",
    "cable_distance_m", "cable_route_notes",
    "site_access_notes", "grid_connection_number", "sanctioned_load_kw",
    "grid_suitable", "grid_notes",
    "recommended_system_type", "recommended_capacity_kw",
    "critical_load_kw", "backup_duration_hours",
    "surveyed_at",
]

# A measured length, area or capacity must be a real positive number.
# Cable distance in particular feeds the cable quantity in F04.
SMALLEST_MEASUREMENT = Decimal("0.01")
POSITIVE_MEASUREMENTS = [
    "roof_length_m", "roof_width_m", "usable_area_sqm",
    "cable_distance_m", "recommended_capacity_kw",
]

# "Not decided" is for an enquiry. A survey has to recommend something.
RECOMMENDABLE_SYSTEM_TYPES = [
    (SystemType.ON_GRID.value, SystemType.ON_GRID.label),
    (SystemType.OFF_GRID.value, SystemType.OFF_GRID.label),
]


class SurveyPhotoSerializer(serializers.ModelSerializer):
    url = serializers.SerializerMethodField()

    class Meta:
        model = SurveyPhoto
        fields = ["id", "url", "caption", "uploaded_at"]

    def get_url(self, photo) -> str:
        """Goes through an authorized view. Uploads are never served directly."""
        return reverse("survey-photo-file", args=[photo.id])


class SurveyRevisionSerializer(serializers.ModelSerializer):
    """One revision, as read."""

    photos = SurveyPhotoSerializer(many=True, read_only=True)
    surveyed_by_name = serializers.CharField(
        source="surveyed_by.__str__", default="", read_only=True
    )
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.__str__", default="", read_only=True
    )
    is_editable = serializers.BooleanField(read_only=True)

    class Meta:
        model = SurveyRevision
        fields = [
            "id", "revision_number", "status", "is_editable",
            *MEASUREMENT_FIELDS,
            "surveyed_by", "surveyed_by_name",
            "submitted_at", "reviewed_by", "reviewed_by_name",
            "reviewed_at", "review_notes", "photos", "created_at",
            "revision",
        ]
        read_only_fields = [
            "revision_number", "status", "surveyed_by",
            "submitted_at", "reviewed_by", "reviewed_at", "review_notes",
        ]


class SurveySerializer(serializers.ModelSerializer):
    """A survey with its whole revision history, newest first."""

    revisions = SurveyRevisionSerializer(many=True, read_only=True)
    enquiry_reference = serializers.CharField(
        source="enquiry.reference", read_only=True
    )
    customer_name = serializers.CharField(
        source="enquiry.site.customer.full_name", read_only=True
    )
    site_state = serializers.CharField(source="enquiry.site.state", read_only=True)
    is_approved = serializers.SerializerMethodField()

    class Meta:
        model = Survey
        fields = [
            "id", "enquiry", "enquiry_reference", "customer_name",
            "is_approved", "revisions", "created_at",
            "assigned_to", "revision",
            "site_state",
        ]

    def get_is_approved(self, survey) -> bool:
        # Reads the prefetched rows. Survey.is_approved would run one
        # more query for every survey in a list.
        return any(
            revision.status == RevisionStatus.APPROVED
            for revision in survey.revisions.all()
        )


class RevisionCreateSerializer(serializers.ModelSerializer):
    """
    Starts a new draft revision.

    The survey and the surveying technician come from the URL and the
    session, never the request body.
    """

    recommended_system_type = serializers.ChoiceField(
        choices=RECOMMENDABLE_SYSTEM_TYPES
    )

    class Meta:
        model = SurveyRevision
        fields = MEASUREMENT_FIELDS
        extra_kwargs = {
            field: {"min_value": SMALLEST_MEASUREMENT}
            for field in POSITIVE_MEASUREMENTS
        }

    def validate_surveyed_at(self, value):
        """A visit that has not happened yet cannot have been measured."""
        if value > timezone.now():
            raise serializers.ValidationError(
                "A survey cannot be recorded in the future."
            )
        return value

    def validate(self, data):
        # Runs the model's own checks, so the off-grid and usable-area
        # rules apply however a revision is created.
        instance = SurveyRevision(**data)
        from django.core.exceptions import ValidationError
        try:
            instance.clean()
        except ValidationError as exc:
            raise serializers.ValidationError(getattr(exc, "message_dict", {"non_field_errors": exc.messages}))
        return data


class SurveyStartSerializer(serializers.Serializer):
    """Which enquiry to open a survey for."""

    enquiry = serializers.IntegerField()


class SurveyPhotoCreateSerializer(serializers.Serializer):
    """One photo added to a draft revision."""

    image = serializers.ImageField()
    caption = serializers.CharField(max_length=200, required=False, allow_blank=True)

    def validate_image(self, value):
        return validate_image(value)


class ReviewSerializer(serializers.Serializer):
    """An approver's decision on a submitted revision."""

    decision = serializers.ChoiceField(
        choices=["approved", "changes_requested", "rejected"]
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
