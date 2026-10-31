"""
Survey API (F03).

    GET  /api/v1/surveys/                      list
    GET  /api/v1/surveys/<id>/                 one survey, all revisions
    POST /api/v1/surveys/start/                open a survey for an enquiry
    POST /api/v1/surveys/<id>/revisions/       add a draft revision
    POST /api/v1/revisions/<id>/submit/        send for review
    POST /api/v1/revisions/<id>/review/        approve, bounce or reject

Transitions go through the model so the same rules apply however a
change is triggered.
"""

from django.core.exceptions import ValidationError
from django.db import IntegrityError
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customers.models import Enquiry

from .models import Survey, SurveyRevision
from .serializers import (
    RevisionCreateSerializer,
    ReviewSerializer,
    SurveyRevisionSerializer,
    SurveySerializer,
)


class SurveyListView(generics.ListAPIView):
    """Surveys, with their revisions. ?pending=true for the review queue."""

    serializer_class = SurveySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Survey.objects.select_related(
            "enquiry", "enquiry__site__customer"
        ).prefetch_related("revisions__photos")

        if self.request.query_params.get("pending") == "true":
            queryset = queryset.filter(revisions__status="submitted").distinct()

        return queryset


class SurveyDetailView(generics.RetrieveAPIView):
    serializer_class = SurveySerializer
    permission_classes = [IsAuthenticated]
    queryset = Survey.objects.prefetch_related("revisions__photos")


class SurveyStartView(APIView):
    """
    Opens the survey for an enquiry.

    One survey per enquiry, so calling this twice returns the existing
    one rather than creating a second.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        enquiry_id = request.data.get("enquiry")
        enquiry = Enquiry.objects.filter(pk=enquiry_id).first()
        if enquiry is None:
            return Response(
                {"enquiry": ["No enquiry with that id."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        survey, created = Survey.objects.get_or_create(enquiry=enquiry)
        return Response(
            SurveySerializer(survey).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class RevisionCreateView(APIView):
    """
    Adds a draft revision to a survey.

    This is also how a technician answers a request for changes: the
    bounced revision stays as it was, and the corrected measurements
    become revision n+1.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        survey = Survey.objects.filter(pk=pk).first()
        if survey is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if survey.is_approved:
            return Response(
                {"detail": "This survey is already approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = RevisionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        revision = SurveyRevision(
            survey=survey,
            surveyed_by=request.user,
            **serializer.validated_data,
        )
        try:
            revision.save()
        except (ValidationError, IntegrityError) as exc:
            return Response(
                {"detail": _describe(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(
            SurveyRevisionSerializer(revision).data,
            status=status.HTTP_201_CREATED,
        )


class RevisionSubmitView(APIView):
    """Sends a draft revision for review."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        revision = SurveyRevision.objects.filter(pk=pk).first()
        if revision is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        try:
            revision.submit()
        except ValidationError as exc:
            return Response(
                {"detail": _describe(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(SurveyRevisionSerializer(revision).data)


class RevisionReviewView(APIView):
    """
    Records the approver's decision.

    Approving unlocks quotation generation for this enquiry, so the
    model checks the reviewer's role rather than trusting the caller.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        revision = SurveyRevision.objects.filter(pk=pk).first()
        if revision is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            revision.review(
                serializer.validated_data["decision"],
                reviewer=request.user,
                notes=serializer.validated_data.get("notes", ""),
            )
        except (ValidationError, IntegrityError) as exc:
            return Response(
                {"detail": _describe(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        return Response(SurveyRevisionSerializer(revision).data)


def _describe(exception):
    """Pulls a readable sentence out of a Django or database error."""
    messages = getattr(exception, "messages", None)
    return messages[0] if messages else str(exception)
