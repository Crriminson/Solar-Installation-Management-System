"""
F16 endpoints.

Two kinds, and the difference matters:

  Staff endpoints are role-gated like everything else.

  Public link endpoints are reached by a customer with no account and
  no session. The token in the URL is the whole authorisation, so each
  one re-checks that the link is live before it offers an action, and
  returns only that link's own document. Nothing here can be made to
  disclose another record (spec.md F16 Security).
"""

from rest_framework.generics import ListAPIView
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import BoundedPagination, StaffAccess
from apps.customers.models import Customer
from apps.documents import services as documents
from apps.quotations.models import AcceptanceChannel, QuoteRevision, QuoteStatus
from apps.quotations.serializers import PresentationSerializer
from apps.quotations.services import accept_quote, transition
from apps.support.models import ServiceTicket
from apps.support.services import confirm_resolution

from . import outbox, services
from .models import IncomingUpdate, LinkPurpose, TelegramBinding
from .serializers import BindingSerializer, IncomingUpdateSerializer

# Who may link a customer, send them a document, or read their replies.
MESSAGING_ROLES = (Role.SALES, Role.OPERATIONS_MANAGER, Role.SUPPORT)


class MessagingAccess(StaffAccess):
    def has_permission(self, request, view):
        view.read_roles = (*MESSAGING_ROLES, Role.DIRECTOR, Role.FINANCE)
        view.write_roles = MESSAGING_ROLES
        return super().has_permission(request, view)


# ============================================================
# Staff: linking a chat
# ============================================================

class IssueLinkToken(APIView):
    """Issues the code a customer sends to the bot to link their chat."""

    permission_classes = [MessagingAccess]

    def post(self, request, pk):
        customer = Customer.objects.filter(pk=pk).first()
        if customer is None:
            return Response({"detail": "That customer does not exist."}, status=404)

        token = services.issue_link_token(customer, request.user)
        return Response({
            "token": token.token,
            "deep_link": services.deep_link(token),
            "expires_at": token.expires_at,
            # Said once. The code is not retrievable afterwards.
            "note": "Send this to the customer now. It is shown only here.",
        }, status=201)


class BindingList(ListAPIView):
    permission_classes = [MessagingAccess]
    serializer_class = BindingSerializer
    pagination_class = BoundedPagination

    def get_queryset(self):
        bindings = TelegramBinding.objects.select_related("customer")
        customer = self.request.query_params.get("customer")
        return bindings.filter(customer=customer) if customer else bindings


class RevokeBinding(APIView):
    """Stops a chat receiving anything. Outstanding links die with it."""

    permission_classes = [MessagingAccess]

    def post(self, request, pk):
        binding = TelegramBinding.objects.filter(pk=pk, revoked_at__isnull=True).first()
        if binding is None:
            return Response({"detail": "No live binding with that id."}, status=404)

        services.revoke_binding(binding, request.user, request.data.get("reason", ""))
        return Response(BindingSerializer(binding).data)


# ============================================================
# Staff: sending the two links
# ============================================================

class SendQuotation(APIView):
    """
    Sends the issued quotation PDF and a single-use signing link.

    The document is generated first so the customer receives the same
    bytes the office holds, and the message is queued rather than sent,
    so a Telegram outage cannot affect the quotation.
    """

    permission_classes = [MessagingAccess]

    def post(self, request, pk):
        revision = QuoteRevision.objects.filter(pk=pk).select_related(
            "quote", "customer").first()
        if revision is None:
            return Response({"detail": "That quotation does not exist."}, status=404)

        document = documents.generate_quotation(revision, request.user)
        link = services.issue_quotation_link(revision, request.user)

        outbox.queue(
            link.binding.chat_id,
            _quotation_message(revision, link),
            dedupe_key=f"quotation:{revision.pk}:{link.token}",
            document=document,
        )
        return Response({"queued": True, "link_expires_at": link.expires_at}, status=201)


class SendTicketConfirmation(APIView):
    """Asks the customer to confirm a repair is resolved (F13)."""

    permission_classes = [MessagingAccess]

    def post(self, request, pk):
        ticket = ServiceTicket.objects.filter(pk=pk).select_related("customer").first()
        if ticket is None:
            return Response({"detail": "That ticket does not exist."}, status=404)

        link = services.issue_ticket_link(ticket, request.user)
        outbox.queue(
            link.binding.chat_id,
            _ticket_message(ticket, link),
            dedupe_key=f"ticket:{ticket.pk}:{link.token}",
        )
        return Response({"queued": True, "link_expires_at": link.expires_at}, status=201)


class Inbox(ListAPIView):
    """What customers have sent, read by staff inside the application."""

    permission_classes = [MessagingAccess]
    serializer_class = IncomingUpdateSerializer
    pagination_class = BoundedPagination

    def get_queryset(self):
        updates = IncomingUpdate.objects.select_related("binding", "binding__customer")
        customer = self.request.query_params.get("customer")
        return updates.filter(binding__customer=customer) if customer else updates


# ============================================================
# Public: what the customer's browser reaches
# ============================================================

class PublicLink(APIView):
    """
    The document behind a link.

    Always answers, even for a spent or expired link, because spec.md
    F06 says a dead link shows its document read-only and offers
    nothing. `state` is what the page uses to decide.
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request, token):
        link = services.open_link(token)
        if link is None:
            return Response({"detail": "This link is not valid."}, status=404)

        body = {"purpose": link.purpose, "state": link.state,
                "expires_at": link.expires_at}

        if link.purpose == LinkPurpose.SIGN_QUOTATION:
            body["document"] = PresentationSerializer(link.quotation).data
        else:
            ticket = link.ticket
            body["ticket"] = {
                "reference": ticket.reference,
                "status": ticket.status,
                "fault": ticket.fault_description,
            }
        return Response(body)


class PublicAccept(APIView):
    """
    The customer's decision, from their own phone.

    The link is spent first and under a lock, so two taps cannot both
    sign. There is no witness here: the verified binding and the
    single-use token are the evidence in its place (spec.md F06).
    """

    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, token):
        link = services.open_link(token)
        if link is None:
            return Response({"detail": "This link is not valid."}, status=404)
        if not link.is_usable:
            return Response({"detail": "This link has already been used or has expired.",
                             "state": link.state}, status=409)

        if link.purpose == LinkPurpose.SIGN_QUOTATION:
            return self._sign(request, link)
        return self._confirm(request, link)

    def _sign(self, request, link):
        """
        Accept or decline, from the customer's own phone.

        Declining is a real answer, not a failure: it closes the
        quotation with the customer's own name as the reason, and the
        link is spent either way so neither answer can be given twice.
        """
        name = (request.data.get("customer_name") or "").strip()
        declined = request.data.get("decision") == "declined"
        signature = request.data.get("signature")

        if not name:
            return Response({"detail": "Type your name first."}, status=400)
        if not declined and not signature:
            return Response({"detail": "Sign before accepting."}, status=400)

        services.spend_link(link)

        if declined:
            transition(
                link.quotation, QuoteStatus.REJECTED, None,
                reason=f"Declined by {name} over Telegram.",
            )
            return Response({"declined": True})

        accept_quote(
            link.quotation,
            {"customer_name": name, "signature": signature},
            actor=None,
            channel=AcceptanceChannel.REMOTE,
        )
        return Response({"accepted": True})

    def _confirm(self, request, link):
        """
        Closing goes through F13's own service, not round it. That
        service holds the rule that a ticket closes on recorded
        customer confirmation and nothing else, and the database has a
        constraint behind it.
        """
        name = (request.data.get("customer_name") or "").strip()
        if not name:
            return Response({"detail": "Type your name to confirm."}, status=400)

        ticket = link.ticket
        services.spend_link(link)
        try:
            confirm_resolution(
                ticket.pk,
                {"customer_name": name, "revision": ticket.revision},
                actor=None,
            )
        except DRFValidationError as exc:
            return Response({"detail": exc.detail}, status=400)
        return Response({"confirmed": True})


# ============================================================
# What the messages say
# ============================================================

def _quotation_message(revision, link):
    return (
        f"Your quotation {revision.quote.reference} is ready.\n\n"
        f"Total payable: INR {revision.gross_payable_incl_tax} including GST\n"
        f"Valid until: {revision.valid_until}\n\n"
        f"Read it and accept or decline here:\n{services._link_url(link)}\n\n"
        "The link works once and then expires."
    )


def _ticket_message(ticket, link):
    return (
        f"About your service request {ticket.reference}.\n\n"
        "Our technician has recorded the work as finished. "
        "Please confirm it is resolved, or tell us it is not:\n"
        f"{services._link_url(link)}\n\n"
        "The link works once and then expires."
    )
