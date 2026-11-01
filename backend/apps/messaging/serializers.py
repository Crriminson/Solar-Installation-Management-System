"""F16 payloads. Read-only: bindings and replies are made by events."""

from rest_framework import serializers

from .models import IncomingUpdate, TelegramBinding


class BindingSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source="customer.full_name", read_only=True)
    is_live = serializers.BooleanField(read_only=True)

    class Meta:
        model = TelegramBinding
        # chat_id is included because staff need to tell two chats apart.
        fields = ("id", "customer", "customer_name", "chat_id", "chat_name",
                  "linked_at", "revoked_at", "revoked_reason", "is_live")
        read_only_fields = fields


class IncomingUpdateSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(
        source="binding.customer.full_name", read_only=True, default="")

    class Meta:
        model = IncomingUpdate
        fields = ("id", "chat_id", "text", "received_at", "handled_at",
                  "binding", "customer_name")
        read_only_fields = fields
