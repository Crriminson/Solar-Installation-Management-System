"""
API endpoints for F01.

Two endpoints:

    POST /api/v1/enquiries/   public, anyone can submit the web form
    GET  /api/v1/enquiries/   staff only, the sales queue

The public endpoint is the one place an unauthenticated person can
write to the database, so it is rate limited and accepts only the
fields on the form.
"""

from django.core.exceptions import ValidationError
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import ContactLog, Enquiry, OPEN_STATUSES
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
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        enquiry = serializer.save()

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
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # select_related avoids one extra query per row for the site,
        # its customer and the owner.
        queryset = Enquiry.objects.select_related(
            "site", "site__customer", "owner"
        )

        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(reference__icontains=search)
                | Q(site__customer__full_name__icontains=search)
                | Q(site__customer__phone__icontains=search)
            )

        if params.get("status"):
            queryset = queryset.filter(status=params["status"])

        # Manager views: the two ways a lead goes quiet.
        if params.get("unassigned") == "true":
            queryset = queryset.filter(owner__isnull=True, status__in=OPEN_STATUSES)

        if params.get("overdue") == "true":
            queryset = queryset.filter(
                next_action_due__lt=timezone.localdate(),
                status__in=OPEN_STATUSES,
            )

        return queryset


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

        owner = get_user_model().objects.filter(pk=data["owner"]).first()
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
