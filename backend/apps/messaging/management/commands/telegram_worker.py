"""
The worker: drains the outbox and long-polls for replies.

Run it beside the server. It is the only process that waits on the
network, which is what keeps a Telegram outage away from the business
transactions (spec.md F16).

    manage.py telegram_worker          # run until stopped
    manage.py telegram_worker --once   # one pass, for a cron or a test
"""

import logging
import time

from django.core.management.base import BaseCommand

from apps.messaging import outbox, services, transport
from apps.messaging.models import IncomingUpdate

logger = logging.getLogger(__name__)

IDLE_SECONDS = 3


class Command(BaseCommand):
    help = "Send queued Telegram messages and collect replies."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true",
                            help="Make a single pass and stop.")
        parser.add_argument("--poll-timeout", type=int, default=25,
                            help="Seconds to hold a long poll open.")

    def handle(self, *args, **options):
        if not transport.is_configured():
            self.stdout.write(self.style.WARNING(
                "TELEGRAM_BOT_TOKEN is not set. The outbox will drain to a fake "
                "transport and nothing will leave this machine."
            ))

        once = options["once"]
        timeout = 0 if once else options["poll_timeout"]

        while True:
            sent, failed = self._drain()
            received = self._collect(timeout)

            if once:
                self.stdout.write(
                    f"sent {sent}, failed {failed}, received {received}"
                )
                return

            if not (sent or received):
                time.sleep(IDLE_SECONDS)

    def _drain(self):
        try:
            return outbox.deliver_pending()
        except Exception:
            # One bad pass must not stop the worker.
            logger.exception("Outbox pass failed.")
            return 0, 0

    def _collect(self, timeout):
        """
        Offset is the highest update seen plus one, which is how
        Telegram is told to stop resending. The unique update_id is the
        backstop if it resends anyway.
        """
        highest = IncomingUpdate.objects.order_by("-update_id").values_list(
            "update_id", flat=True).first()
        offset = (highest + 1) if highest is not None else None

        try:
            updates = transport.get_updates(offset=offset, timeout=timeout)
        except transport.TransportError as exc:
            logger.warning("Could not collect updates: %s", exc)
            return 0

        handled = 0
        for update in updates:
            try:
                if services.handle_update(update) is not None:
                    handled += 1
            except Exception:
                logger.exception("Could not handle update %s", update.get("update_id"))
        return handled
