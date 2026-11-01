"""What a document looks like over the API. Read-only throughout."""

from rest_framework import serializers

from .models import Document


class DocumentSerializer(serializers.ModelSerializer):
    kind_label = serializers.CharField(source="get_kind_display", read_only=True)
    generated_by_name = serializers.CharField(
        source="generated_by.get_full_name", read_only=True, default=""
    )

    class Meta:
        model = Document
        fields = ("id", "kind", "kind_label", "reference", "revision",
                  "content_hash", "generated_at", "generated_by_name")
        read_only_fields = fields
