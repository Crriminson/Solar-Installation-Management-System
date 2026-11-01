"""
What F16 actually does: bind a chat, issue a link, read a reply.

The rule running through all of it (spec.md F16 Security): the bot acts
on a chat because that chat is bound to a verified customer. It never
discloses a record because somebody typed a phone number or a serial
into it, and an unknown chat is answered with an instruction, not with
information.
"""

from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from apps.core.models import record_event

from . import outbox
from .models import (
    CustomerLink, IncomingUpdate, LinkPurpose, LinkToken, TelegramBinding,
)

# What an unknown chat is told. It names no customer and confirms
# nothing about who we do or do not have on file.
UNKNOWN_CHAT_REPLY = (
    "This chat is not linked to a customer account. "
    "Ask the team for a linking code, then send it here."
)

LINKED_REPLY = (
    "Thanks - this chat is now linked. "
    "You will get your quotation, documents and visit updates here."
)

SPENT_TOKEN_REPLY = (
    "That code has already been used or has expired. "
    "Ask the team for a new one."
)


# ============================================================
# Linking a chat to a customer
# ============================================================

@transaction.atomic
def issue_link_token(customer, actor=None):
    """
    Staff issue a code for the customer to send to the bot.

    Returned once and never shown again, in the same way a password is
    not. The deep link carries it so the customer only has to tap.
    """
    token = LinkToken.objects.create(
        customer=customer,
        issued_by=actor,
        expires_at=timezone.now() + timedelta(
            minutes=settings.TELEGRAM_LINK_TOKEN_MINUTES
        ),
    )
    record_event(customer, "telegram_link_token_issued", actor=actor, reason="")
    return token


def deep_link(token):
    """t.me/<bot>?start=<token> - tapping it sends the code for them."""
    username = settings.TELEGRAM_BOT_USERNAME
    if not username:
        return ""
    return f"https://t.me/{username}?start={token.token}"


@transaction.atomic
def bind_chat(token_value, chat_id, chat_name=""):
    """
    Spend a linking token and bind the chat. Returns the binding, or
    None when the code is unusable.

    Locked for update because two messages from the same chat arriving
    together must not create two bindings.
    """
    token = (
        LinkToken.objects
        .select_for_update()
        .filter(token=token_value)
        .select_related("customer")
        .first()
    )
    if token is None or not token.is_usable:
        return None

    # A chat already bound elsewhere is released first, so one chat is
    # never live against two customers.
    TelegramBinding.objects.filter(
        chat_id=str(chat_id), revoked_at__isnull=True
    ).update(revoked_at=timezone.now(), revoked_reason="Re-linked to another customer")

    binding = TelegramBinding.objects.create(
        customer=token.customer, chat_id=str(chat_id), chat_name=chat_name,
        linked_by=token.issued_by,
    )
    token.spent_at = timezone.now()
    token.binding = binding
    token.save(update_fields=["spent_at", "binding"])

    record_event(token.customer, "telegram_chat_linked", actor=token.issued_by, reason="")
    return binding


@transaction.atomic
def revoke_binding(binding, actor, reason):
    """
    Stops the chat receiving anything, at once.

    Outstanding links die with it: a link is only usable while its
    binding is live, so nothing has to be hunted down.
    """
    if not reason.strip():
        raise ValidationError({"reason": "Say why this chat is being unlinked."})

    binding.revoked_at = timezone.now()
    binding.revoked_by = actor
    binding.revoked_reason = reason
    binding.save(update_fields=["revoked_at", "revoked_by", "revoked_reason"])

    record_event(binding.customer, "telegram_chat_revoked", actor=actor, reason=reason)
    return binding


# ============================================================
# The two links a customer is ever sent
# ============================================================

def _link_url(link):
    base = settings.PUBLIC_BASE_URL
    path = (
        f"/sign/{link.token}" if link.purpose == LinkPurpose.SIGN_QUOTATION
        else f"/confirm/{link.token}"
    )
    return f"{base}{path}" if base else path


@transaction.atomic
def issue_quotation_link(revision, actor):
    """
    A single-use link to accept or decline one exact revision.

    Issuing invalidates every outstanding link for the same quotation,
    which is spec.md F06: reissuing a quotation must make the old link
    useless rather than leave two signable documents in the wild.
    """
    customer = revision.customer
    binding = _live_binding(customer)
    if binding is None:
        raise ValidationError(
            "This customer has no linked Telegram chat. "
            "Issue a linking code first, or sign under supervision."
        )

    CustomerLink.objects.filter(
        quotation__quote=revision.quote,
        spent_at__isnull=True, invalidated_at__isnull=True,
    ).update(invalidated_at=timezone.now())

    link = CustomerLink.objects.create(
        purpose=LinkPurpose.SIGN_QUOTATION, binding=binding, quotation=revision,
        document_revision=revision.revision,
        expires_at=timezone.now() + timedelta(hours=settings.CUSTOMER_LINK_HOURS),
    )
    record_event(revision, "telegram_signing_link_issued", actor=actor, reason="")
    return link


@transaction.atomic
def issue_ticket_link(ticket, actor):
    """A single-use link for the customer to confirm a repair is done."""
    binding = _live_binding(ticket.customer)
    if binding is None:
        raise ValidationError(
            "This customer has no linked Telegram chat. "
            "Record their confirmation by phone instead."
        )

    CustomerLink.objects.filter(
        ticket=ticket, spent_at__isnull=True, invalidated_at__isnull=True,
    ).update(invalidated_at=timezone.now())

    link = CustomerLink.objects.create(
        purpose=LinkPurpose.CONFIRM_TICKET, binding=binding, ticket=ticket,
        expires_at=timezone.now() + timedelta(hours=settings.CUSTOMER_LINK_HOURS),
    )
    record_event(ticket, "telegram_confirmation_link_issued", actor=actor, reason="")
    return link


def open_link(token_value):
    """
    The link as the customer's browser finds it.

    Always returns the record so a spent or expired link can still show
    its document read-only, which is what spec.md F06 asks for. The
    caller checks `is_usable` before offering any action.
    """
    return (
        CustomerLink.objects
        .select_related("binding", "quotation", "quotation__quote", "ticket")
        .filter(token=token_value)
        .first()
    )


@transaction.atomic
def spend_link(link):
    """
    Marks a link used. Locked, because two taps on the same link must
    not both succeed.
    """
    locked = CustomerLink.objects.select_for_update().get(pk=link.pk)
    if not locked.is_usable:
        raise ValidationError("This link has already been used or has expired.")
    locked.spent_at = timezone.now()
    locked.save(update_fields=["spent_at"])
    return locked


def _live_binding(customer):
    return (
        TelegramBinding.objects
        .filter(customer=customer, revoked_at__isnull=True)
        .order_by("-id")
        .first()
    )


# ============================================================
# Reading what the customer sends
# ============================================================

@transaction.atomic
def handle_update(update):
    """
    Record one Telegram update and answer it.

    Deduplicated by update_id: long polling can hand the same update
    over twice and the database refuses the second. Returns the stored
    row, or None when it was a duplicate.
    """
    message = update.get("message") or update.get("edited_message") or {}
    chat = message.get("chat") or {}
    chat_id = str(chat.get("id", ""))
    text = (message.get("text") or "").strip()

    if not chat_id:
        return None

    binding = TelegramBinding.objects.filter(
        chat_id=chat_id, revoked_at__isnull=True
    ).select_related("customer").first()

    stored, created = IncomingUpdate.objects.get_or_create(
        update_id=update["update_id"],
        defaults={"chat_id": chat_id, "text": text,
                  "payload": message, "binding": binding},
    )
    if not created:
        return None

    _answer(stored, text, chat_id, chat, binding)
    return stored


def _answer(stored, text, chat_id, chat, binding):
    """A linking code binds the chat; anything else is a message to staff."""
    code = _linking_code(text)

    if code:
        name = " ".join(filter(None, [chat.get("first_name"), chat.get("last_name")]))
        new_binding = bind_chat(code, chat_id, chat_name=name)
        reply = LINKED_REPLY if new_binding else SPENT_TOKEN_REPLY
        outbox.queue(chat_id, reply, dedupe_key=f"reply:{stored.update_id}")
        if new_binding:
            stored.binding = new_binding
        stored.handled_at = timezone.now()
        stored.save(update_fields=["binding", "handled_at"])
        return

    if binding is None:
        outbox.queue(chat_id, UNKNOWN_CHAT_REPLY, dedupe_key=f"reply:{stored.update_id}")
        stored.handled_at = timezone.now()
        stored.save(update_fields=["handled_at"])
        return

    # A linked customer talking: staff read it in the app. The bot
    # relays and collects; it does not answer questions about a record.
    outbox.queue(
        chat_id,
        "Thanks - the team has your message and will come back to you here.",
        dedupe_key=f"reply:{stored.update_id}",
    )


def _linking_code(text):
    """`/start <code>` from the deep link, or the bare code pasted in."""
    if text.startswith("/start"):
        parts = text.split(maxsplit=1)
        return parts[1].strip() if len(parts) > 1 else ""
    if text and " " not in text and len(text) >= 32:
        return text
    return ""
