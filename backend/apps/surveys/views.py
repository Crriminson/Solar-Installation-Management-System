"""
Survey API (F03).

    GET  /api/v1/surveys/                      list
    GET  /api/v1/surveys/<id>/                 one survey, all revisions
    POST /api/v1/surveys/start/                open a survey for an enquiry
    POST /api/v1/surveys/<id>/revisions/       add a draft revision
    POST /api/v1/revisions/<id>/submit/        send for review
    POST /api/v1/revisions/<id>/review/        approve, bounce or reject
    POST /api/v1/revisions/<id>/photos/        add a photo to a draft
    GET  /api/v1/survey-photos/<id>/           view a photo

Transitions go through the model so the same rules apply however a
change is triggered.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.customers.models import Enquiry

from .models import RevisionStatus, Survey, SurveyPhoto, SurveyRevision
from .serializers import (
    RevisionCreateSerializer,
    ReviewSerializer,
    SurveyPhotoCreateSerializer,
    SurveyPhotoSerializer,
    SurveyRevisionSerializer,
    SurveySerializer,
    SurveyStartSerializer,
)


def surveys_with_history():
    """
    Surveys with everything their serializer reads, joined up front.

    Without this a list runs one more query per survey, per revision,
    for every name and photo it shows.
    """
    revisions = SurveyRevision.objects.select_related(
        "surveyed_by", "reviewed_by"
    ).prefetch_related("photos")

    return Survey.objects.select_related(
        "enquiry", "enquiry__site__customer"
    ).prefetch_related(Prefetch("revisions", queryset=revisions))


class SurveyListView(generics.ListAPIView):
    """
    Surveys, with their revisions.

    ?pending=true for the review queue, ?open=true for surveys not yet
    approved, ?search= across enquiry reference and customer name.
    """

    serializer_class = SurveySerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = surveys_with_history()
        params = self.request.query_params

        if params.get("pending") == "true":
            queryset = queryset.filter(
                revisions__status=RevisionStatus.SUBMITTED
            ).distinct()

        if params.get("open") == "true":
            queryset = queryset.exclude(revisions__status=RevisionStatus.APPROVED)

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(enquiry__reference__icontains=search)
                | Q(enquiry__site__customer__full_name__icontains=search)
            )

        return queryset


class SurveyDetailView(generics.RetrieveAPIView):
    serializer_class = SurveySerializer
    permission_classes = [IsAuthenticated]
    queryset = surveys_with_history()


class SurveyStartView(APIView):
    """
    Opens the survey for an enquiry.

    One survey per enquiry, so calling this twice returns the existing
    one rather than creating a second.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = SurveyStartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        enquiry = Enquiry.objects.filter(pk=serializer.validated_data["enquiry"]).first()
        if enquiry is None:
            return Response(
                {"enquiry": ["No enquiry with that id."]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # A lost lead has nothing left to survey. One already surveyed
        # still opens, because its history stays readable.
        if not enquiry.is_open and not Survey.objects.filter(enquiry=enquiry).exists():
            return Response(
                {"enquiry": ["This enquiry is closed."]},
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
        except ValidationError as exc:
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
        except ValidationError as exc:
            return Response(
                {"detail": _describe(exc)}, status=status.HTTP_400_BAD_REQUEST
            )
        except IntegrityError:
            # The partial unique index refused a second approved
            # revision. Say so plainly rather than echo the database.
            return Response(
                {"detail": "Another revision of this survey is already approved."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(SurveyRevisionSerializer(revision).data)


class RevisionPhotoView(APIView):
    """
    Adds a photo to a draft revision.

    Only a draft: once submitted, a revision is evidence, and that
    includes what was attached to it.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        revision = SurveyRevision.objects.filter(pk=pk).first()
        if revision is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not revision.is_editable:
            return Response(
                {"detail": "Photos can only be added to a draft."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if revision.photos.count() >= settings.MAX_PHOTOS_PER_RECORD:
            return Response(
                {"detail": f"A revision can hold {settings.MAX_PHOTOS_PER_RECORD} photos."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        serializer = SurveyPhotoCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        photo = SurveyPhoto.objects.create(revision=revision, **serializer.validated_data)
        return Response(
            SurveyPhotoSerializer(photo).data, status=status.HTTP_201_CREATED
        )


class SurveyPhotoFileView(APIView):
    """Serves a photo, after checking the viewer is signed in."""

    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        photo = SurveyPhoto.objects.filter(pk=pk).first()
        if photo is None:
            raise Http404

        return FileResponse(photo.image.open("rb"))


def _describe(exception):
    """Pulls a readable sentence out of a Django error."""
    messages = getattr(exception, "messages", None)
    return messages[0] if messages else str(exception)
