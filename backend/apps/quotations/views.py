"""Sales generates/issues quotation revisions; directors can read frozen selling documents."""

from django.db.models import Q
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import StaffAccess, business_date
from apps.core.models import AuditEvent
from apps.core.serializers import AuditEventSerializer
from django.shortcuts import get_object_or_404
from .models import QuoteRevision, QuoteStatus
from rest_framework.parsers import FormParser, MultiPartParser

from .serializers import (AcceptSerializer, ActionSerializer, GenerateSerializer,
                          PresentationSerializer, QuoteSerializer)
from .services import generate_quote, quote_action


class QuoteAccess(StaffAccess):
    def has_permission(self, request, view):
        view.read_roles = (Role.SALES, Role.OPERATIONS_MANAGER, Role.DIRECTOR)
        view.write_roles = (Role.SALES,)
        return super().has_permission(request, view)


def quotations_with_lines():
    return QuoteRevision.objects.select_related("quote", "survey_revision").prefetch_related("lines")


class QuoteListView(generics.ListAPIView):
    permission_classes = [QuoteAccess]
    serializer_class = QuoteSerializer

    def get_queryset(self):
        queryset = quotations_with_lines()
        params = self.request.query_params
        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(Q(quote__reference__icontains=search) | Q(snapshot__customer__name__icontains=search))
        state = params.get("status")
        if state == QuoteStatus.EXPIRED:
            queryset = queryset.filter(Q(status=state) | Q(status=QuoteStatus.ISSUED, valid_until__lt=business_date()))
        elif state == QuoteStatus.ISSUED:
            queryset = queryset.filter(status=state, valid_until__gte=business_date())
        elif state:
            queryset = queryset.filter(status=state)
        if params.get("enquiry"):
            queryset = queryset.filter(quote__enquiry_id=params["enquiry"])
        ordering = {"created": "created_at", "-created": "-created_at", "amount": "gross_payable_incl_tax",
                    "-amount": "-gross_payable_incl_tax"}.get(params.get("sort"), "-created_at")
        return queryset.order_by(ordering, "-id")


class QuoteDetailView(generics.RetrieveAPIView):
    permission_classes = [QuoteAccess]
    serializer_class = QuoteSerializer
    queryset = quotations_with_lines()


class QuoteGenerateView(APIView):
    permission_classes = [QuoteAccess]

    def post(self, request):
        serializer = GenerateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quotation = generate_quote(serializer.validated_data, request.user)
        return Response(QuoteSerializer(quotation, context={"request": request}).data, status=201)


class QuoteActivityView(generics.ListAPIView):
    permission_classes = [QuoteAccess]
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        quotation = get_object_or_404(QuoteRevision, pk=self.kwargs["pk"])
        return AuditEvent.objects.filter(record_type="quotations.quoterevision", record_id=quotation.pk).select_related("actor")


class QuoteActionView(APIView):
    permission_classes = [QuoteAccess]

    def post(self, request, pk, action):
        serializer = ActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quotation = quote_action(pk, action, serializer.validated_data, request.user)
        return Response(QuoteSerializer(quotation, context={"request": request}).data)


class QuotePresentView(generics.RetrieveAPIView):
    """
    The restricted view a customer is handed the tablet to read.

    Same staff sign-in as everything else, because the device belongs to
    the staff member. What changes is the payload: one document, no
    actions, no record ids, nobody else's data.
    """

    permission_classes = [QuoteAccess]
    serializer_class = PresentationSerializer
    queryset = quotations_with_lines()


class QuoteAcceptView(APIView):
    """
    Takes the customer's signature and accepts the quotation.

    Separate from the generic action route because it carries a file, but
    it goes through the same locked, idempotent action path so acceptance
    obeys the same concurrency rules as every other document action.
    """

    permission_classes = [QuoteAccess]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        serializer = AcceptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        quotation = quote_action(pk, "accept", serializer.validated_data, request.user)
        return Response(QuoteSerializer(quotation, context={"request": request}).data)
