"""Append-only evidence for business transitions and controlled corrections."""

from django.conf import settings
from django.db import models
import logging

LOGGER = logging.getLogger(__name__)


class AuditEvent(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True)
    record_type = models.CharField(max_length=80)
    record_id = models.PositiveBigIntegerField()
    action = models.CharField(max_length=80)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        indexes = [models.Index(fields=["record_type", "record_id"])]


def record_event(record, action, actor=None, *, before=None, after=None, reason=""):
    """Write alongside the business change, inside the caller's transaction."""
    event = AuditEvent.objects.create(
        actor=actor, record_type=record._meta.label_lower, record_id=record.pk,
        action=action, before=before or {}, after=after or {}, reason=reason,
    )
    LOGGER.info("%s record=%s:%s actor=%s", action, event.record_type, record.pk, event.actor_id)
    return event
