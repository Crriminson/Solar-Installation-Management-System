"""
F16 - the customer's channel, without building them a dashboard.

Five records carry the whole feature:

  TelegramBinding  which chat belongs to which verified customer
  LinkToken        the staff-issued, single-use token that creates one
  CustomerLink     a single-use link to one document or ticket
  OutboxMessage    something to send, with its retries
  IncomingUpdate   something received, recorded once

The security rule underneath all of it: the bot answers a chat because
that chat is bound to a customer, never because someone typed a phone
number or a serial into it.
"""

import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone


def new_token():
    """URL-safe and long enough that guessing is not a strategy."""
    return secrets.token_urlsafe(32)


# ============================================================
# Who a chat belongs to
# ============================================================

class TelegramBinding(models.Model):
    """
    A verified link between one Telegram chat and one customer.

    Revocable, and revoking is what a customer gets instead of a
    password reset: the chat stops receiving anything at once. A revoked
    binding is kept rather than deleted, so the history of who was told
    what survives.
    """

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="telegram_bindings"
    )
    chat_id = models.CharField(max_length=40)
    chat_name = models.CharField(max_length=150, blank=True)

    linked_at = models.DateTimeField(auto_now_add=True)
    # Null when the customer linked themselves from the enquiry form.
    linked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="bindings_created",
    )
    revoked_at = models.DateTimeField(null=True, blank=True)
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="bindings_revoked",
    )
    revoked_reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            # One live binding per chat. A chat that was revoked can be
            # bound again, which is why this is conditional.
            models.UniqueConstraint(
                fields=["chat_id"], condition=models.Q(revoked_at__isnull=True),
                name="one_live_binding_per_chat",
            ),
        ]

    def __str__(self):
        return f"{self.customer} on chat {self.chat_id}"

    @property
    def is_live(self):
        return self.revoked_at is None


class LinkToken(models.Model):
    """
    Staff issue this, the customer sends it to the bot, and the binding
    is made. Single-use and expiring, so a token read over someone's
    shoulder is worth nothing for long.
    """

    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, related_name="link_tokens"
    )
    token = models.CharField(max_length=64, unique=True, default=new_token)
    issued_at = models.DateTimeField(auto_now_add=True)
    # Null when the public enquiry form issued it: the customer is
    # linking to the record they just created themselves, so there is no
    # staff member to name.
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="link_tokens_issued",
    )
    expires_at = models.DateTimeField()
    spent_at = models.DateTimeField(null=True, blank=True)
    binding = models.OneToOneField(
        TelegramBinding, on_delete=models.PROTECT,
        null=True, blank=True, related_name="link_token",
    )

    class Meta:
        ordering = ["-id"]

    def save(self, *args, **kwargs):
        if not self.pk and not self.expires_at:
            self.expires_at = timezone.now() + timedelta(
                minutes=settings.TELEGRAM_LINK_TOKEN_MINUTES
            )
        super().save(*args, **kwargs)

    @property
    def is_usable(self):
        return self.spent_at is None and timezone.now() < self.expires_at


# ============================================================
# What the customer is asked to do
# ============================================================

class LinkPurpose(models.TextChoices):
    """
    The two things a customer is ever asked to do from a message.

    Installation acceptance is not here: spec.md F11 has the customer
    sign on the crew's device at the site, not from a link.
    """

    SIGN_QUOTATION = "sign_quotation", "Accept or decline a quotation"
    CONFIRM_TICKET = "confirm_ticket", "Confirm a repair is resolved"


class CustomerLink(models.Model):
    """
    One link, one document, one chat, one use.

    Spec.md F06 and F16: it is single-use, it expires, it is bound to
    the chat of a verified customer, and it names the exact revision it
    was issued for. Reissuing the document invalidates every outstanding
    link for it. A spent or expired link shows its document read-only
    and offers nothing, which is why spending it does not delete it.
    """

    purpose = models.CharField(max_length=20, choices=LinkPurpose.choices)
    token = models.CharField(max_length=64, unique=True, default=new_token)
    binding = models.ForeignKey(
        TelegramBinding, on_delete=models.PROTECT, related_name="links"
    )

    # Exactly one of these, matching the purpose.
    quotation = models.ForeignKey(
        "quotations.QuoteRevision", on_delete=models.PROTECT,
        null=True, blank=True, related_name="customer_links",
    )
    ticket = models.ForeignKey(
        "support.ServiceTicket", on_delete=models.PROTECT,
        null=True, blank=True, related_name="customer_links",
    )

    # The revision the link was issued against. A document that moves on
    # leaves the link pointing at something the customer never saw.
    document_revision = models.PositiveIntegerField(default=1)

    issued_at = models.DateTimeField(auto_now_add=True)
    expires_at = models.DateTimeField()
    spent_at = models.DateTimeField(null=True, blank=True)
    invalidated_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-id"]
        indexes = [models.Index(fields=["purpose", "spent_at"])]
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(purpose="sign_quotation", quotation__isnull=False)
                    | models.Q(purpose="confirm_ticket", ticket__isnull=False)
                ),
                name="customer_link_matches_its_record",
            ),
        ]

    def __str__(self):
        return f"{self.get_purpose_display()} for chat {self.binding.chat_id}"

    @property
    def is_usable(self):
        return (
            self.spent_at is None
            and self.invalidated_at is None
            and self.binding.is_live
            and timezone.now() < self.expires_at
        )

    @property
    def state(self):
        """Why a link cannot be used, for a page that must explain itself."""
        if self.spent_at is not None:
            return "spent"
        if self.invalidated_at is not None:
            return "superseded"
        if not self.binding.is_live:
            return "revoked"
        if timezone.now() >= self.expires_at:
            return "expired"
        return "open"


# ============================================================
# Sending and receiving
# ============================================================

class OutboxStatus(models.TextChoices):
    PENDING = "pending", "Waiting to send"
    SENT = "sent", "Sent"
    FAILED = "failed", "Gave up"


class OutboxMessage(models.Model):
    """
    Something to send, written inside the business transaction and sent
    long after it commits.

    That order is the whole point (spec.md F16): a Telegram outage must
    never roll back or corrupt the business action that triggered the
    message. The worker drains this table; nothing calls the network
    while a stock or payment transaction is open.
    """

    chat_id = models.CharField(max_length=40)
    text = models.TextField()
    document = models.ForeignKey(
        "documents.Document", on_delete=models.PROTECT,
        null=True, blank=True, related_name="outbox_messages",
    )

    # Two identical sends of the same event collapse into one row, so a
    # retried business action cannot message the customer twice.
    dedupe_key = models.CharField(max_length=120, unique=True)

    status = models.CharField(
        max_length=20, choices=OutboxStatus.choices, default=OutboxStatus.PENDING
    )
    attempts = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(default=timezone.now)
    last_error = models.TextField(blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    sent_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["status", "next_attempt_at"])]

    def __str__(self):
        return f"{self.status} to {self.chat_id}"


class IncomingUpdate(models.Model):
    """
    One update from Telegram, recorded once.

    `update_id` is unique, which is the deduplication spec.md F16 asks
    for: long polling can hand the same update over twice, and the
    database refuses the second one.
    """

    update_id = models.BigIntegerField(unique=True)
    chat_id = models.CharField(max_length=40)
    text = models.TextField(blank=True)
    payload = models.JSONField(default=dict)
    received_at = models.DateTimeField(auto_now_add=True)
    handled_at = models.DateTimeField(null=True, blank=True)

    # Set when the chat was recognised. An update from an unknown chat
    # is kept, but it never causes a record to be disclosed.
    binding = models.ForeignKey(
        TelegramBinding, on_delete=models.PROTECT,
        null=True, blank=True, related_name="updates",
    )

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"update {self.update_id} from {self.chat_id}"

    def delete(self, *args, **kwargs):
        raise ValidationError("Received messages are evidence and are not deleted.")
