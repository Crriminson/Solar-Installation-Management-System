"""API contracts for F10."""

from rest_framework import serializers

from .models import Job, JobAssignment, JobKind, ScheduleChange


# ============================================================
# Inputs
# ============================================================

class RevisionSerializer(serializers.Serializer):
    revision = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=3000, required=False, allow_blank=True)


class JobCreateSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(choices=JobKind.choices)
    site = serializers.IntegerField(min_value=1)
    order = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    survey = serializers.IntegerField(min_value=1, required=False, allow_null=True)
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()
    notes = serializers.CharField(max_length=3000, required=False, allow_blank=True)

    # First in the list becomes the lead, so a crew always has one name
    # to ask for on site.
    technicians = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )


class RescheduleSerializer(RevisionSerializer):
    starts_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField()


class ScheduleSerializer(RescheduleSerializer):
    """Booking a job that awaits scheduling: its slot and crew together."""

    notes = serializers.CharField(max_length=3000, required=False, allow_blank=True)
    technicians = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=False
    )


class OrderReferenceSerializer(serializers.Serializer):
    order = serializers.IntegerField(min_value=1)


class BlockSerializer(RevisionSerializer):
    owner = serializers.IntegerField(min_value=1)


# ============================================================
# Outputs
# ============================================================

class AssignmentSerializer(serializers.ModelSerializer):
    technician_name = serializers.CharField(
        source="technician.get_full_name", read_only=True, default=""
    )
    username = serializers.CharField(source="technician.username", read_only=True)

    class Meta:
        model = JobAssignment
        fields = ["id", "technician", "technician_name", "username", "is_lead"]


class ScheduleChangeSerializer(serializers.ModelSerializer):
    changed_by_name = serializers.CharField(
        source="changed_by.get_full_name", read_only=True, default=""
    )

    class Meta:
        model = ScheduleChange
        fields = ["id", "previous_starts_at", "previous_ends_at", "reason",
                  "changed_by", "changed_by_name", "changed_at"]


class JobSerializer(serializers.ModelSerializer):
    """
    A job as the office sees it.

    Technicians get TechnicianJobSerializer instead, which carries less.
    """

    customer_name = serializers.CharField(source="site.customer.full_name", read_only=True)
    site_address = serializers.SerializerMethodField()
    order_reference = serializers.CharField(
        source="order.reference", read_only=True, default=""
    )
    assignments = AssignmentSerializer(many=True, read_only=True)
    schedule_changes = ScheduleChangeSerializer(many=True, read_only=True)
    is_blocked = serializers.BooleanField(read_only=True)

    class Meta:
        model = Job
        fields = ["id", "kind", "status", "site", "site_address", "customer_name",
                  "order", "order_reference", "survey", "starts_at", "ends_at",
                  "notes", "is_blocked", "blocked_reason", "blocked_owner",
                  "cancelled_reason", "revision", "created_at",
                  "assignments", "schedule_changes"]

    def get_site_address(self, job):
        site = job.site
        return f"{site.address_line}, {site.city}, {site.state} {site.pincode}"


class TechnicianJobSerializer(JobSerializer):
    """
    What a technician is shown: the job, and what they need to do it.

    No order reference, no reschedule history, no blocked owner. Spec.md
    F10 asks for the detail the job requires and no more.
    """

    class Meta(JobSerializer.Meta):
        fields = ["id", "kind", "status", "site_address", "customer_name",
                  "starts_at", "ends_at", "notes", "is_blocked", "blocked_reason",
                  "revision", "assignments"]
