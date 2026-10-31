"""
API endpoints for F01.

Two endpoints:

    POST /api/v1/enquiries/   public, anyone can submit the web form
    GET  /api/v1/enquiries/   staff only, the sales queue

The public endpoint is the one place an unauthenticated person can
write to the database, so it is rate limited and accepts only the
fields on the form.
"""

from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .models import Enquiry
from .serializers import EnquiryCreateSerializer, EnquiryListSerializer


class PublicEnquiryThrottle(AnonRateThrottle):
    """Limits how often one anonymous client can submit the form."""

    rate = "20/hour"


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
        # select_related avoids one extra query per row for the site
        # and its customer.
        queryset = Enquiry.objects.select_related("site", "site__customer")

        search = self.request.query_params.get("search", "").strip()
        if search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(reference__icontains=search)
                | Q(site__customer__full_name__icontains=search)
                | Q(site__customer__phone__icontains=search)
            )

        return queryset
