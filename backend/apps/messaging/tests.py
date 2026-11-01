"""
F16 - what has to hold however Telegram behaves.

The expensive mistakes here are a network failure corrupting a business
action, the same message arriving twice, a link that still works after
it has been used, and the bot telling a stranger about a customer.
"""

from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import Role
from apps.customers.models import Customer, Site
from apps.support.tests import SupportFixture
from apps.messaging import outbox, services, transport
from apps.messaging.models import (
    CustomerLink, IncomingUpdate, LinkPurpose, OutboxMessage, OutboxStatus,
    TelegramBinding,
)

User = get_user_model()
JSON = "application/json"


class MessagingFixture(TestCase):
    def setUp(self):
        transport.reset()
        self.sales = User.objects.create_user("msg_sales", roles=[Role.SALES])
        self.warehouse = User.objects.create_user("msg_wh", roles=[Role.WAREHOUSE])
        self.customer = Customer.objects.create(
            full_name="Meera Pillai", phone="9876500000", email="",
            customer_type="residential",
        )
        Site.objects.create(
            customer=self.customer, address_line="12 Anna Nagar", city="Chennai",
            state="TN", pincode="600040", address_key="12annanagar600040",
        )

    def bind(self, chat_id="555"):
        return TelegramBinding.objects.create(
            customer=self.customer, chat_id=chat_id, linked_by=self.sales,
        )


# ============================================================
# The outbox guarantee
# ============================================================

class OutboxTests(MessagingFixture):
    def test_a_telegram_outage_leaves_the_message_queued_not_lost(self):
        """Spec.md F16: an outage must not corrupt the business action."""
        self.bind()
        outbox.queue_for_customer(self.customer, "Your order is on its way.", "order:1")

        with patch.object(transport, "send_message",
                          side_effect=transport.TransportError("network down")):
            sent, failed = outbox.deliver_pending()

        message = OutboxMessage.objects.get()
        self.assertEqual((sent, failed), (0, 1))
        self.assertEqual(message.status, OutboxStatus.PENDING)
        self.assertEqual(message.attempts, 1)
        self.assertGreater(message.next_attempt_at, timezone.now())

    def test_it_sends_once_telegram_comes_back(self):
        self.bind()
        outbox.queue_for_customer(self.customer, "Delivered.", "delivery:1")

        with patch.object(transport, "send_message",
                          side_effect=transport.TransportError("down")):
            outbox.deliver_pending()

        OutboxMessage.objects.update(next_attempt_at=timezone.now())
        with patch.object(transport, "send_message", return_value={"message_id": 1}):
            sent, failed = outbox.deliver_pending()

        self.assertEqual((sent, failed), (1, 0))
        self.assertEqual(OutboxMessage.objects.get().status, OutboxStatus.SENT)

    def test_it_gives_up_rather_than_retrying_forever(self):
        self.bind()
        outbox.queue_for_customer(self.customer, "Hello.", "hello:1")

        with patch.object(transport, "send_message",
                          side_effect=transport.TransportError("blocked")):
            for _ in range(10):
                OutboxMessage.objects.update(next_attempt_at=timezone.now())
                outbox.deliver_pending()

        self.assertEqual(OutboxMessage.objects.get().status, OutboxStatus.FAILED)

    def test_the_same_event_cannot_message_the_customer_twice(self):
        self.bind()
        outbox.queue_for_customer(self.customer, "Delivered.", "delivery:7")
        outbox.queue_for_customer(self.customer, "Delivered.", "delivery:7")
        self.assertEqual(OutboxMessage.objects.count(), 1)

    def test_an_unlinked_customer_is_not_an_error(self):
        """Telegram is a channel a customer may simply not have."""
        self.assertIsNone(
            outbox.queue_for_customer(self.customer, "Hello.", "hello:2"))
        self.assertEqual(OutboxMessage.objects.count(), 0)

    def test_a_revoked_chat_receives_nothing(self):
        binding = self.bind()
        services.revoke_binding(binding, self.sales, "Customer asked to unlink.")
        self.assertIsNone(
            outbox.queue_for_customer(self.customer, "Hello.", "hello:3"))


# ============================================================
# Incoming
# ============================================================

class IncomingTests(MessagingFixture):
    def update(self, update_id, text, chat_id="555"):
        return {"update_id": update_id,
                "message": {"text": text, "chat": {"id": chat_id, "first_name": "Meera"}}}

    def test_the_same_update_is_recorded_once(self):
        """Long polling can hand the same update over twice."""
        self.bind()
        self.assertIsNotNone(services.handle_update(self.update(1, "Hello")))
        self.assertIsNone(services.handle_update(self.update(1, "Hello")))
        self.assertEqual(IncomingUpdate.objects.count(), 1)

    def test_an_unknown_chat_is_told_nothing_about_any_customer(self):
        services.handle_update(self.update(2, "What is my order status?", chat_id="999"))
        reply = OutboxMessage.objects.get().text
        self.assertIn("not linked", reply)
        self.assertNotIn(self.customer.full_name, reply)
        self.assertNotIn(self.customer.phone, reply)

    def test_a_phone_number_does_not_unlock_a_record(self):
        """Spec.md F16: never disclose a record because someone typed a
        phone number or a serial into the chat."""
        services.handle_update(self.update(3, self.customer.phone, chat_id="999"))
        reply = OutboxMessage.objects.get().text
        self.assertNotIn(self.customer.full_name, reply)
        self.assertFalse(TelegramBinding.objects.exists())

    def test_a_linking_code_binds_the_chat(self):
        token = services.issue_link_token(self.customer, self.sales)
        services.handle_update(self.update(4, f"/start {token.token}", chat_id="777"))

        binding = TelegramBinding.objects.get()
        self.assertEqual(binding.customer, self.customer)
        self.assertEqual(binding.chat_id, "777")

    def test_a_code_works_once(self):
        token = services.issue_link_token(self.customer, self.sales)
        services.handle_update(self.update(5, f"/start {token.token}", chat_id="777"))
        services.handle_update(self.update(6, f"/start {token.token}", chat_id="888"))
        self.assertEqual(TelegramBinding.objects.filter(revoked_at__isnull=True).count(), 1)

    def test_an_expired_code_does_not_bind(self):
        token = services.issue_link_token(self.customer, self.sales)
        token.expires_at = timezone.now() - timedelta(minutes=1)
        token.save(update_fields=["expires_at"])
        services.handle_update(self.update(7, f"/start {token.token}", chat_id="777"))
        self.assertFalse(TelegramBinding.objects.exists())


# ============================================================
# The customer's link
# ============================================================

class LinkTests(SupportFixture, TestCase):
    """
    A ticket belongs to an order (D054), so these reuse F13's own
    fixture rather than inventing half a chain.
    """

    def setUp(self):
        super().setUp()
        transport.reset()
        self.binding = TelegramBinding.objects.create(
            customer=self.order.customer, chat_id="555", linked_by=self.manager,
        )

    def ticket_link(self):
        return CustomerLink.objects.create(
            purpose=LinkPurpose.CONFIRM_TICKET, binding=self.binding,
            ticket=self.raise_ticket(),
            expires_at=timezone.now() + timedelta(hours=1),
        )

    def test_a_link_works_once(self):
        link = self.ticket_link()
        services.spend_link(link)
        link.refresh_from_db()
        self.assertFalse(link.is_usable)
        self.assertEqual(link.state, "spent")

    def test_an_expired_link_is_not_usable(self):
        link = self.ticket_link()
        link.expires_at = timezone.now() - timedelta(minutes=1)
        link.save(update_fields=["expires_at"])
        self.assertEqual(link.state, "expired")

    def test_revoking_the_chat_kills_its_outstanding_links(self):
        link = self.ticket_link()
        services.revoke_binding(link.binding, self.manager, "Customer asked.")
        link.refresh_from_db()
        self.assertFalse(link.is_usable)
        self.assertEqual(link.state, "revoked")

    def test_a_dead_link_still_answers_so_the_page_can_explain_itself(self):
        link = self.ticket_link()
        services.spend_link(link)
        self.client.logout()
        response = self.client.get(reverse("public-link", args=[link.token]))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["state"], "spent")

    def test_a_dead_link_refuses_the_action(self):
        link = self.ticket_link()
        services.spend_link(link)
        self.client.logout()
        response = self.client.post(
            reverse("public-link-accept", args=[link.token]),
            {"customer_name": "Meera"}, content_type=JSON)
        self.assertEqual(response.status_code, 409)

    def test_an_invented_token_finds_nothing(self):
        self.client.logout()
        response = self.client.get(reverse("public-link", args=["not-a-real-token"]))
        self.assertEqual(response.status_code, 404)


# ============================================================
# Permissions (rules.md section 4)
# ============================================================

class PermissionTests(MessagingFixture):
    def test_the_warehouse_cannot_link_a_customers_chat(self):
        self.client.force_login(self.warehouse)
        response = self.client.post(
            reverse("telegram-token", args=[self.customer.pk]), {}, content_type=JSON)
        self.assertEqual(response.status_code, 403)

    def test_sales_can(self):
        self.client.force_login(self.sales)
        response = self.client.post(
            reverse("telegram-token", args=[self.customer.pk]), {}, content_type=JSON)
        self.assertEqual(response.status_code, 201)

    def test_the_warehouse_cannot_read_the_inbox(self):
        self.client.force_login(self.warehouse)
        self.assertEqual(self.client.get(reverse("telegram-inbox")).status_code, 403)

    def test_signed_out_staff_endpoints_refuse(self):
        self.assertIn(
            self.client.get(reverse("telegram-inbox")).status_code, (401, 403))

    def test_the_public_link_needs_no_session(self):
        link_token = "x" * 40
        self.assertEqual(
            self.client.get(reverse("public-link", args=[link_token])).status_code, 404)


# ============================================================
# The token is a credential
# ============================================================

class SecretTests(MessagingFixture):
    def test_a_transport_failure_never_repeats_the_token(self):
        """The API URL carries the token, so an error must not carry the URL."""
        with self.settings(TELEGRAM_BOT_TOKEN="123456:SUPERSECRETVALUE"):
            import httpx
            with patch.object(httpx, "post", side_effect=httpx.ConnectError("boom")):
                with self.assertRaises(transport.TransportError) as caught:
                    transport.send_message("555", "hello")
        self.assertNotIn("SUPERSECRETVALUE", str(caught.exception))
