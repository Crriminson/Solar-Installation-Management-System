"""
Survey serializers (F03).

Reading a survey shows every revision, because the history of what was
reported and sent back is part of the record. Writing only ever creates
a new revision — nothing edits a reviewed one.
"""

from rest_framework import serializers

from .models import Survey, SurveyPhoto, SurveyRevision


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


class SurveyPhotoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SurveyPhoto
        fields = ["id", "image", "caption", "uploaded_at"]


class SurveyRevisionSerializer(serializers.ModelSerializer):
    """One revision, as read."""

    photos = SurveyPhotoSerializer(many=True, read_only=True)
    surveyed_by_name = serializers.CharField(
        source="surveyed_by.get_full_name", default="", read_only=True
    )
    reviewed_by_name = serializers.CharField(
        source="reviewed_by.get_full_name", default="", read_only=True
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
    is_approved = serializers.BooleanField(read_only=True)

    class Meta:
        model = Survey
        fields = [
            "id", "enquiry", "enquiry_reference", "customer_name",
            "is_approved", "revisions", "created_at",
        ]


class RevisionCreateSerializer(serializers.ModelSerializer):
    """
    Starts a new draft revision.

    The survey and the surveying technician come from the URL and the
    session, never the request body.
    """

    class Meta:
        model = SurveyRevision
        fields = MEASUREMENT_FIELDS

    def validate(self, data):
        # Runs the model's own checks, so the off-grid and usable-area
        # rules apply however a revision is created.
        instance = SurveyRevision(**data)
        instance.clean()
        return data


class ReviewSerializer(serializers.Serializer):
    """An approver's decision on a submitted revision."""

    decision = serializers.ChoiceField(
        choices=["approved", "changes_requested", "rejected"]
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
