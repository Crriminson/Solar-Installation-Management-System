"""
Talking to the Telegram Bot API.

Everything that touches the network lives here, behind two functions,
so the rest of F16 can be tested without a bot and the worker is the
only thing that ever waits on a socket.

With no token configured the fake transport is used instead: the app
runs, the outbox drains, and the tests pass on a machine that has never
spoken to Telegram. Nothing else changes.

The token is a credential. It appears in the URL this module builds and
must never reach a log, an error message or an audit entry, which is
why failures here are reported by status and reason, never by URL.
"""

import logging

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

API_ROOT = "https://api.telegram.org"
REQUEST_TIMEOUT_SECONDS = 20

# Telegram's own cap on a message. Longer text is cut rather than
# rejected, because a truncated status update beats no status update.
MAX_MESSAGE_CHARS = 4096


class TransportError(Exception):
    """Delivery failed. The outbox decides whether to try again."""


def is_configured():
    return bool(settings.TELEGRAM_BOT_TOKEN)


def _url(method):
    return f"{API_ROOT}/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"


def _check(response):
    """
    Telegram answers 200 with ok=false for ordinary refusals, so the
    status code alone does not say whether a message arrived.
    """
    try:
        body = response.json()
    except ValueError as exc:
        raise TransportError(f"Telegram sent a reply that was not JSON ({response.status_code})") from exc

    if not body.get("ok"):
        raise TransportError(body.get("description") or "Telegram refused the request")
    return body["result"]


# ============================================================
# Sending
# ============================================================

def send_message(chat_id, text):
    if not is_configured():
        return _fake_send(chat_id, text)

    try:
        response = httpx.post(
            _url("sendMessage"),
            json={
                "chat_id": chat_id,
                "text": text[:MAX_MESSAGE_CHARS],
                "disable_web_page_preview": True,
            },
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        # The exception's text can carry the URL, and the URL carries
        # the token, so only the class name is repeated.
        raise TransportError(f"Could not reach Telegram ({type(exc).__name__})") from exc

    return _check(response)


def send_document(chat_id, caption, filename, content):
    """Sends a generated PDF with its covering message."""
    if not is_configured():
        return _fake_send(chat_id, caption, filename=filename)

    try:
        response = httpx.post(
            _url("sendDocument"),
            data={"chat_id": chat_id, "caption": caption[:MAX_MESSAGE_CHARS]},
            files={"document": (filename, content, "application/pdf")},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise TransportError(f"Could not reach Telegram ({type(exc).__name__})") from exc

    return _check(response)


# ============================================================
# Receiving
# ============================================================

def get_updates(offset=None, timeout=25):
    """
    Long polling, which spec.md F16 chooses for a local deployment: no
    public webhook endpoint has to exist for the bot to work.
    """
    if not is_configured():
        return []

    try:
        response = httpx.get(
            _url("getUpdates"),
            params={"offset": offset, "timeout": timeout},
            timeout=timeout + REQUEST_TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        raise TransportError(f"Could not reach Telegram ({type(exc).__name__})") from exc

    return _check(response)


# ============================================================
# The fake, for a machine with no bot
# ============================================================

_sent = []


def _fake_send(chat_id, text, filename=None):
    _sent.append({"chat_id": chat_id, "text": text, "filename": filename})
    logger.info("Telegram is not configured; message to %s was not sent.", chat_id)
    return {"message_id": len(_sent), "faked": True}


def sent_messages():
    """What the fake transport has been handed. For tests only."""
    return list(_sent)


def reset():
    """For tests only."""
    _sent.clear()
