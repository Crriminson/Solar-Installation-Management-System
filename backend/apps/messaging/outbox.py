"""
The outbox: queue inside the transaction, send long after it commits.

This is the guarantee spec.md F16 asks for. A business action writes a
row here as part of its own transaction. If the action rolls back the
row goes with it, so nothing is sent about something that did not
happen. If the action commits, the message is owed and the worker will
keep trying until it is delivered or given up on.

No network call ever happens inside a business transaction. A Telegram
outage delays messages; it cannot roll back a delivery, a payment or a
stock movement.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from . import transport
from .models import OutboxMessage, OutboxStatus, TelegramBinding

logger = logging.getLogger(__name__)


def queue(chat_id, text, dedupe_key, document=None):
    """
    Record something to send. Safe to call twice: the dedupe key makes
    the second call a no-op, so a retried business action cannot
    message the customer twice.
    """
    message, _ = OutboxMessage.objects.get_or_create(
        dedupe_key=dedupe_key,
        defaults={"chat_id": chat_id, "text": text, "document": document},
    )
    return message


def queue_for_customer(customer, text, dedupe_key, document=None):
    """
    Send to a customer's live chat, if they have one.

    Returns None when they are not linked or their binding was revoked.
    That is a normal outcome, not an error: Telegram is a channel the
    customer may simply not have.
    """
    binding = (
        TelegramBinding.objects
        .filter(customer=customer, revoked_at__isnull=True)
        .order_by("-id")
        .first()
    )
    if binding is None:
        return None
    return queue(binding.chat_id, text, dedupe_key, document=document)


def queue_after_commit(customer, text, dedupe_key, document=None):
    """
    For callers that would rather not leave a row behind if their own
    transaction fails for an unrelated reason afterwards.

    Most callers want plain queue_for_customer: writing inside the
    transaction is what ties the message to the action succeeding.
    """
    transaction.on_commit(
        lambda: queue_for_customer(customer, text, dedupe_key, document=document)
    )


# ============================================================
# Draining
# ============================================================

def deliver_pending(limit=25):
    """
    Send what is due. Returns (sent, failed).

    One message at a time, each in its own try: one bad chat must not
    stop the queue behind it.
    """
    due = (
        OutboxMessage.objects
        .filter(status=OutboxStatus.PENDING, next_attempt_at__lte=timezone.now())
        .select_related("document")[:limit]
    )

    sent = failed = 0
    for message in due:
        if _deliver_one(message):
            sent += 1
        else:
            failed += 1
    return sent, failed


def _deliver_one(message):
    message.attempts += 1
    try:
        if message.document:
            transport.send_document(
                message.chat_id, message.text,
                f"{message.document.kind}-{message.document.reference}.pdf",
                message.document.file.read(),
            )
        else:
            transport.send_message(message.chat_id, message.text)
    except transport.TransportError as exc:
        _back_off(message, str(exc))
        return False

    message.status = OutboxStatus.SENT
    message.sent_at = timezone.now()
    message.last_error = ""
    message.save(update_fields=["status", "sent_at", "attempts", "last_error"])
    return True


def _back_off(message, reason):
    """
    Wait longer after each failure, and give up eventually.

    A message that can never be delivered - a blocked bot, a deleted
    chat - must not be retried forever, so the queue behind it keeps
    moving.
    """
    message.last_error = reason[:500]
    if message.attempts >= settings.OUTBOX_MAX_ATTEMPTS:
        message.status = OutboxStatus.FAILED
        logger.warning(
            "Giving up on message %s to chat %s after %s attempts.",
            message.pk, message.chat_id, message.attempts,
        )
    else:
        delay = settings.OUTBOX_BACKOFF_SECONDS * (2 ** (message.attempts - 1))
        message.next_attempt_at = timezone.now() + timedelta(seconds=delay)

    message.save(update_fields=["status", "attempts", "next_attempt_at", "last_error"])
