"""
API endpoints for F01 and F02.

    POST /api/v1/enquiries/submit/          public, the web form
    GET  /api/v1/enquiries/                 staff, the sales queue
    GET  /api/v1/enquiries/<id>/bill/       staff, the uploaded bill
    PATCH /api/v1/enquiries/<id>/assign/    staff
    POST /api/v1/enquiries/<id>/status/     staff
    GET, POST /api/v1/enquiries/<id>/contacts/   staff

The public endpoint is the one place an unauthenticated person can
write to the database, so it is rate limited and accepts only the
fields on the form.
"""

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import SalesAccess, business_date, check_revision
from apps.core.models import AuditEvent, record_event
from apps.core.serializers import AuditEventSerializer

from .constants import NATIONAL_PHONE_DIGITS
from .models import ContactLog, Enquiry, EnquirySource, OPEN_STATUSES
from .serializers import (
    ContactLogSerializer,
    EnquiryAssignSerializer,
    EnquiryCreateSerializer,
    EnquiryListSerializer,
    EnquiryStatusChangeSerializer,
)


class PublicEnquiryThrottle(AnonRateThrottle):
    """
    Limits how often one anonymous client can submit the form.

    The rate lives in settings so it can be raised for a demo without
    touching code. All local submissions share one IP, so the default
    is easy to hit while testing.
    """

    scope = "public_enquiry"


class EnquiryCreateView(generics.CreateAPIView):
    """
    Accepts a web enquiry.

    Replies only after the records are committed, and returns the
    reference number so the customer has proof it was received.
    """

    serializer_class = EnquiryCreateSerializer
    permission_classes = [AllowAny]
    throttle_classes = [PublicEnquiryThrottle]

    def create(self, request, *args, **kwargs):
        if request.user.is_authenticated and not SalesAccess().has_permission(request, self):
            self.permission_denied(request, message=SalesAccess.message)
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # Staff say where a phone or walk-in enquiry came from. A visitor
        # is always the web form, whatever the request claims, so source
        # attribution can be trusted.
        if request.user.is_authenticated:
            enquiry = serializer.save()
        else:
            enquiry = serializer.save(source=EnquirySource.WEB_FORM)

        return Response(
            {
                "reference": enquiry.reference,
                "message": "Enquiry received. Our team will contact you shortly.",
            },
            status=status.HTTP_201_CREATED,
        )


class EnquiryListView(generics.ListAPIView):
    """
    The sales queue: every enquiry, newest first.

    Supports ?search= across customer name, phone and reference.
    """

    serializer_class = EnquiryListSerializer
    permission_classes = [SalesAccess]

    def get_queryset(self):
        # select_related avoids one extra query per row for the site,
        # its customer and the owner.
        queryset = Enquiry.objects.select_related(
            "site", "site__customer", "owner", "possible_duplicate_of"
        )

        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            matches = (
                Q(reference__icontains=search)
                | Q(site__customer__full_name__icontains=search)
                | Q(site__customer__phone__icontains=search)
            )

            # Numbers are stored as 10 digits, but staff type them as
            # they read them: +91 98765 43210, 098765-43210.
            digits = "".join(character for character in search if character.isdigit())
            if digits:
                matches |= Q(
                    site__customer__phone__icontains=digits[-NATIONAL_PHONE_DIGITS:]
                )

            queryset = queryset.filter(matches)

        if params.get("status"):
            queryset = queryset.filter(status=params["status"])

        # Manager views: the two ways a lead goes quiet.
        if params.get("unassigned") == "true":
            queryset = queryset.filter(owner__isnull=True, status__in=OPEN_STATUSES)

        if params.get("overdue") == "true":
            queryset = queryset.filter(
                next_action_due__lt=business_date(),
                status__in=OPEN_STATUSES,
            )

        ordering = {"received": "created_at", "-received": "-created_at",
                    "due": "next_action_due", "-due": "-next_action_due"}
        return queryset.order_by(ordering.get(params.get("sort"), "-created_at"), "-id")


class EnquiryBillView(APIView):
    """
    GET /api/v1/enquiries/<id>/bill/

    Customer documents are never served as plain files. Each download
    is authorized here. Sent as an attachment, so a file is saved rather
    than opened inside the app.
    """

    permission_classes = [SalesAccess]

    def get(self, request, pk):
        enquiry = Enquiry.objects.filter(pk=pk).first()
        if enquiry is None or not enquiry.electricity_bill:
            raise Http404

        return FileResponse(
            enquiry.electricity_bill.open("rb"),
            as_attachment=True,
            filename=f"{enquiry.reference}-bill",
        )


# ============================================================
# Follow-up actions (F02)
# ============================================================

class EnquiryAssignView(APIView):
    """
    PATCH /api/v1/enquiries/<id>/assign/

    Gives the enquiry an owner and a planned next action. Both at once,
    deliberately: an owner with nothing scheduled is how a lead goes
    quiet.
    """

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        enquiry = self._get_open_enquiry(pk)
        if isinstance(enquiry, Response):
            return enquiry

        serializer = EnquiryAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from django.contrib.auth import get_user_model

        # Only current staff, so a lead cannot be handed to someone who
        # has left and then wait for them forever.
        owner = get_user_model().objects.filter(
            pk=data["owner"], is_active=True, is_active_staff=True
        ).first()
        if owner is None:
            return Response(
                {"owner": ["No staff member with that id."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        enquiry.owner = owner
        enquiry.next_action = data["next_action"]
        enquiry.next_action_due = data.get("next_action_due")
        enquiry.save(update_fields=["owner", "next_action", "next_action_due"])

        return Response(EnquiryListSerializer(enquiry).data)

    def _get_open_enquiry(self, pk):
        enquiry = Enquiry.objects.filter(pk=pk).first()
        if enquiry is None:
            return Response(status=status.HTTP_404_NOT_FOUND)
        if not enquiry.is_open:
            return Response(
                {"detail": "This enquiry is closed."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return enquiry


class EnquiryStatusView(APIView):
    """
    POST /api/v1/enquiries/<id>/status/

    Asks the model to move the enquiry on. The model owns the rules
    about which moves are legal and what each one requires, so the same
    checks apply however the change is triggered.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        enquiry = Enquiry.objects.filter(pk=pk).first()
        if enquiry is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = EnquiryStatusChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            enquiry.change_status(
                data["status"],
                reason=data.get("reason", ""),
                next_action=data.get("next_action", ""),
                next_action_due=data.get("next_action_due"),
            )
        except ValidationError as exc:
            return Response(
                {"detail": exc.messages[0]}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(EnquiryListSerializer(enquiry).data)


class ContactLogListCreateView(generics.ListCreateAPIView):
    """
    GET  /api/v1/enquiries/<id>/contacts/   the history
    POST /api/v1/enquiries/<id>/contacts/   record an attempt

    An unanswered call is recorded too. Knowing someone tried three
    times is the point of a contact history.
    """

    serializer_class = ContactLogSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return ContactLog.objects.filter(
            enquiry_id=self.kwargs["pk"]
        ).select_related("staff")

    def perform_create(self, serializer):
        # Staff comes from the session, never the request body, so one
        # person cannot file a contact under someone else's name.
        serializer.save(
            enquiry_id=self.kwargs["pk"], staff=self.request.user
        )


class DuplicateReviewView(APIView):
    """Resolve a flag explicitly without merging or discarding incoming records."""

    permission_classes = [SalesAccess]

    @transaction.atomic
    def post(self, request, pk):
        enquiry = get_object_or_404(Enquiry.objects.select_for_update(), pk=pk)
        check_revision(enquiry, request.data)
        decision = request.data.get("decision")
        reason = str(request.data.get("reason", "")).strip()
        if decision not in ("confirmed", "distinct") or not reason:
            return Response({"reason": ["Choose confirmed or distinct and record the review reason."]}, status=400)
        if not enquiry.possible_duplicate_of_id or enquiry.duplicate_review:
            return Response({"detail": "There is no pending duplicate flag."}, status=400)
        enquiry.duplicate_review = decision
        enquiry.duplicate_review_reason = reason
        enquiry.revision += 1
        enquiry.save()
        record_event(enquiry, "duplicate_reviewed", request.user,
                     after={"decision": decision, "candidate_customer": enquiry.possible_duplicate_of_id},
                     reason=reason)
        return Response(EnquiryListSerializer(enquiry).data)


class EnquiryActivityView(generics.ListAPIView):
    """Read the actor and before/after evidence behind the enquiry's history."""

    permission_classes = [SalesAccess]
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        pk = self.kwargs["pk"]
        get_object_or_404(Enquiry, pk=pk)
        return AuditEvent.objects.filter(record_type="customers.enquiry", record_id=pk).select_related("actor")
