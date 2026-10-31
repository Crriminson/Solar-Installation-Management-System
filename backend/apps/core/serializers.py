"""The record timeline exposes actors, reasons and timestamps without internal payloads."""

from rest_framework import serializers
from .models import AuditEvent


class AuditEventSerializer(serializers.ModelSerializer):
    actor_name = serializers.CharField(source="actor.username", default="System / public intake")

    class Meta:
        model = AuditEvent
        fields = ["id", "action", "actor_name", "reason", "created_at"]
