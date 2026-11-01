"""
Installation evidence endpoints (F11).

    GET  /api/v1/installations/                  list
    GET  /api/v1/installations/<id>/             one report
    POST /api/v1/installations/open/             start the on-site form
    POST /api/v1/installations/<id>/update/      save measurements
    POST /api/v1/installations/<id>/units/       record a fitted serial
    POST /api/v1/installations/<id>/photos/      attach captioned evidence
    GET  /api/v1/installations/photos/<id>/file/ one photo, to who may see the report
    POST /api/v1/installations/<id>/submit/      freeze and show the customer
    POST /api/v1/installations/<id>/decide/      accept or refuse

The crew fills this in on a phone at the site, so technicians can write
here. They see their own jobs' reports and nothing else.
"""

from django.http import FileResponse, Http404
from rest_framework import generics
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import StaffAccess

from .models import InstallationPhoto, InstallationReport
from .serializers import (AcceptanceSerializer, DecisionSerializer,
                          InstalledUnitReadSerializer, InstalledUnitSerializer,
                          PhotoReadSerializer, PhotoSerializer, ReportSerializer,
                          ReportUpdateSerializer, RevisionSerializer)
from .services import (add_installed_unit, decide, open_report, submit_report,
                       update_report)


class InstallationAccess(StaffAccess):
    """The crew records the work; the office reads it."""

    def has_permission(self, request, view):
        view.read_roles = (Role.TECHNICIAN, Role.OPERATIONS_MANAGER, Role.SUPPORT,
                           Role.SALES, Role.DIRECTOR)
        view.write_roles = (Role.TECHNICIAN, Role.OPERATIONS_MANAGER)
        return super().has_permission(request, view)


def reports_with_evidence():
    return (InstallationReport.objects
            .select_related("job__site__customer", "job__order", "acceptance")
            .prefetch_related("installed_units__unit__product", "photos"))


def is_office(user):
    return user.has_any_role(Role.OPERATIONS_MANAGER, Role.SUPPORT,
                             Role.SALES, Role.DIRECTOR)


def scoped_reports(queryset, user):
    """The reports this person may see: all for the office, own jobs for a crew."""
    if is_office(user):
        return queryset
    return queryset.filter(job__assignments__technician=user)


class ReportListView(generics.ListAPIView):
    permission_classes = [InstallationAccess]
    serializer_class = ReportSerializer

    def get_queryset(self):
        queryset = scoped_reports(reports_with_evidence(), self.request.user)
        if self.request.query_params.get("status"):
            queryset = queryset.filter(status=self.request.query_params["status"])
        return queryset.distinct()


class ReportDetailView(generics.RetrieveAPIView):
    permission_classes = [InstallationAccess]
    serializer_class = ReportSerializer

    def get_queryset(self):
        return scoped_reports(reports_with_evidence(), self.request.user).distinct()


class ReportOpenView(APIView):
    permission_classes = [InstallationAccess]

    def post(self, request):
        report = open_report(request.data.get("job"), request.user)
        return Response(
            ReportSerializer(reports_with_evidence().get(pk=report.pk)).data, status=201
        )


class ReportUpdateView(APIView):
    permission_classes = [InstallationAccess]

    def post(self, request, pk):
        serializer = ReportUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        update_report(pk, serializer.validated_data, request.user)
        return Response(ReportSerializer(reports_with_evidence().get(pk=pk)).data)


class InstalledUnitView(APIView):
    permission_classes = [InstallationAccess]

    def post(self, request, pk):
        serializer = InstalledUnitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        entry = add_installed_unit(pk, serializer.validated_data, request.user)
        return Response(InstalledUnitReadSerializer(entry).data, status=201)


class PhotoView(APIView):
    permission_classes = [InstallationAccess]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        report = InstallationReport.objects.filter(pk=pk).first()
        if report is None:
            return Response(status=404)
        if not report.is_editable:
            return Response({"status": ["This report is closed."]}, status=400)

        serializer = PhotoSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        photo = InstallationPhoto.objects.create(report=report, **serializer.validated_data)
        return Response(PhotoReadSerializer(photo).data, status=201)


class PhotoFileView(APIView):
    """
    Serves one photo of the work, after checking the viewer may see it.

    Uploads live in private storage and are never served as plain files:
    a photo of somebody's roof is shown only to those who may see that
    report. A crew asking for another crew's photo gets a 404, the same
    answer as for a photo that does not exist.
    """

    permission_classes = [InstallationAccess]

    def get(self, request, pk):
        photo = InstallationPhoto.objects.filter(pk=pk).first()
        visible = photo is not None and scoped_reports(
            InstallationReport.objects.filter(pk=photo.report_id), request.user).exists()
        if not visible:
            raise Http404
        return FileResponse(photo.image.open("rb"))


class ReportSubmitView(APIView):
    permission_classes = [InstallationAccess]

    def post(self, request, pk):
        serializer = RevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        submit_report(pk, serializer.validated_data, request.user)
        return Response(ReportSerializer(reports_with_evidence().get(pk=pk)).data)


class ReportDecideView(APIView):
    """Carries the customer's signature, so it takes multipart."""

    permission_classes = [InstallationAccess]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        serializer = DecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        acceptance = decide(pk, serializer.validated_data, request.user)
        return Response(AcceptanceSerializer(acceptance).data, status=201)
