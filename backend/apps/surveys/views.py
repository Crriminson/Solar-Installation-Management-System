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
from django.db import transaction
from django.db.models import Prefetch, Q
from django.http import FileResponse, Http404
from django.shortcuts import get_object_or_404
from django.contrib.auth import get_user_model
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.exceptions import PermissionDenied

from apps.customers.models import Enquiry
from apps.accounts.models import Role
from apps.core.api import check_revision
from apps.core.models import AuditEvent, record_event
from apps.core.serializers import AuditEventSerializer
from .permissions import SurveyAccess, scoped_surveys, require_capture

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


def locked_revision(pk):
    """All revision actions lock the survey first, matching review and quotation generation."""
    revision = SurveyRevision.objects.filter(pk=pk).first()
    if revision is None:
        return None
    Survey.objects.select_for_update().get(pk=revision.survey_id)
    return SurveyRevision.objects.select_for_update().get(pk=pk)


class SurveyListView(generics.ListAPIView):
    """
    Surveys, with their revisions.

    ?pending=true for the review queue, ?open=true for surveys not yet
    approved, ?search= across enquiry reference and customer name.
    """

    serializer_class = SurveySerializer
    permission_classes = [SurveyAccess]

    def get_queryset(self):
        queryset = scoped_surveys(surveys_with_history(), self.request.user)
        params = self.request.query_params
        if params.get("approved") == "true":
            queryset = queryset.filter(revisions__status=RevisionStatus.APPROVED)

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
    permission_classes = [SurveyAccess]
    def get_queryset(self):
        return scoped_surveys(surveys_with_history(), self.request.user)


class RevisionActivityView(generics.ListAPIView):
    permission_classes = [SurveyAccess]
    serializer_class = AuditEventSerializer

    def get_queryset(self):
        revision = get_object_or_404(SurveyRevision, pk=self.kwargs["pk"])
        if not scoped_surveys(Survey.objects.filter(pk=revision.survey_id), self.request.user).exists():
            raise Http404
        return AuditEvent.objects.filter(record_type="surveys.surveyrevision", record_id=revision.pk).select_related("actor")


class SurveyAssignView(APIView):
    """Operations hands the requested visit to an active technician."""

    permission_classes = [SurveyAccess]

    @transaction.atomic
    def post(self, request, pk):
        if not request.user.has_role(Role.OPERATIONS_MANAGER):
            raise PermissionDenied("Only Operations may assign a survey.")
        survey = get_object_or_404(Survey.objects.select_for_update(), pk=pk)
        check_revision(survey, request.data)
        technician_id = request.data.get("assigned_to")
        if not isinstance(technician_id, int):
            return Response({"assigned_to": ["Choose a technician."]}, status=400)
        technician = get_user_model().objects.filter(pk=technician_id, is_active=True, is_active_staff=True).first()
        if not technician or not technician.has_role(Role.TECHNICIAN):
            return Response({"assigned_to": ["Choose an active Technician."]}, status=400)
        previous = survey.assigned_to_id
        survey.assigned_to = technician
        survey.revision += 1
        survey.save()
        record_event(survey, "assigned", request.user, before={"assigned_to": previous},
                     after={"assigned_to": technician.pk})
        return Response(SurveySerializer(survey).data)


class RevisionEditView(APIView):
    """Correct a draft or requested revision; submitted and approved evidence stays frozen."""

    permission_classes = [SurveyAccess]

    @transaction.atomic
    def patch(self, request, pk):
        revision = locked_revision(pk)
        if revision is None:
            raise Http404
        require_capture(revision.survey, request.user)
        check_revision(revision, request.data)
        if not revision.is_editable:
            return Response({"detail": "Only a draft or Changes Requested revision can be corrected."}, status=400)
        serializer = RevisionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        before = revision.measurement_snapshot()
        changed_time = revision.surveyed_at != serializer.validated_data["surveyed_at"]
        reason = str(request.data.get("reason", "")).strip()
        if changed_time and not reason:
            return Response({"reason": ["Explain the correction to the actual survey time."]}, status=400)
        for field, value in serializer.validated_data.items():
            setattr(revision, field, value)
        revision.save()
        record_event(revision, "corrected", request.user, before=before,
                     after=revision.measurement_snapshot(), reason=reason)
        return Response(SurveyRevisionSerializer(revision).data)


class SurveyStartView(APIView):
    """
    Opens the survey for an enquiry.

    One survey per enquiry, so calling this twice returns the existing
    one rather than creating a second.
    """

    permission_classes = [SurveyAccess]

    @transaction.atomic
    def post(self, request):
        if not request.user.has_any_role(Role.SALES, Role.OPERATIONS_MANAGER):
            raise PermissionDenied("Sales or Operations must request the survey.")
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
        if created:
            record_event(survey, "requested", request.user, after={"enquiry": enquiry.pk})
        return Response(
            SurveySerializer(survey).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class RevisionCreateView(APIView):
    """
    Adds a draft revision to a survey.

    An approved survey is changed through a new revision. Requested
    corrections use RevisionEditView and resubmit the existing revision.
    An earlier approval stands until its replacement is approved.
    """

    permission_classes = [SurveyAccess]

    @transaction.atomic
    def post(self, request, pk):
        survey = scoped_surveys(Survey.objects.select_for_update(), request.user).filter(pk=pk).first()
        if survey is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        require_capture(survey, request.user)
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

    permission_classes = [SurveyAccess]

    @transaction.atomic
    def post(self, request, pk):
        revision = locked_revision(pk)
        if revision is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        require_capture(revision.survey, request.user)
        check_revision(revision, request.data)
        try:
            revision.submit(actor=request.user)
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

    permission_classes = [SurveyAccess]

    @transaction.atomic
    def post(self, request, pk):
        revision = locked_revision(pk)
        if revision is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        if not request.user.has_role(Role.OPERATIONS_MANAGER):
            raise PermissionDenied("Only an operations manager may review a survey.")
        check_revision(revision, request.data)
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

        return Response(SurveyRevisionSerializer(revision).data)


class RevisionPhotoView(APIView):
    """
    Adds a photo to a draft revision.

    Only a draft: once submitted, a revision is evidence, and that
    includes what was attached to it.
    """

    permission_classes = [SurveyAccess]

    @transaction.atomic
    def post(self, request, pk):
        revision = locked_revision(pk)
        if revision is None:
            return Response(status=status.HTTP_404_NOT_FOUND)

        require_capture(revision.survey, request.user)
        if not revision.is_editable:
            return Response(
                {"detail": "Photos can only be added to a draft or a requested correction."},
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

    permission_classes = [SurveyAccess]

    def get(self, request, pk):
        photo = SurveyPhoto.objects.filter(pk=pk).first()
        if photo is None or not scoped_surveys(Survey.objects.filter(pk=photo.revision.survey_id), request.user).exists():
            raise Http404

        return FileResponse(photo.image.open("rb"))


def _describe(exception):
    """Pulls a readable sentence out of a Django error."""
    messages = getattr(exception, "messages", None)
    return messages[0] if messages else str(exception)
