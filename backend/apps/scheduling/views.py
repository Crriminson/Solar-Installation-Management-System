"""
Scheduling endpoints (F10).

    GET  /api/v1/jobs/                   the diary
    GET  /api/v1/jobs/<id>/              one job
    POST /api/v1/jobs/create/            book a visit and staff it
    POST /api/v1/jobs/<id>/reschedule/   move it, with a reason
    POST /api/v1/jobs/<id>/block/        record a delay against an owner
    POST /api/v1/jobs/<id>/start/        crew on site
    POST /api/v1/jobs/<id>/cancel/       call it off

A technician sees only their own jobs, and a thinner payload: spec.md
F10 asks for the detail the job requires and no more.
"""

from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import StaffAccess

from .models import Job
from .serializers import (BlockSerializer, JobCreateSerializer, JobSerializer,
                          RescheduleSerializer, RevisionSerializer,
                          TechnicianJobSerializer)
from .services import block_job, cancel_job, create_job, reschedule_job, start_job


class SchedulingAccess(StaffAccess):
    """Managers book the work; technicians read their own."""

    def has_permission(self, request, view):
        view.read_roles = (Role.OPERATIONS_MANAGER, Role.TECHNICIAN, Role.SUPPORT,
                           Role.SALES, Role.DIRECTOR)
        view.write_roles = (Role.OPERATIONS_MANAGER,)
        return super().has_permission(request, view)


def jobs_with_detail():
    return (Job.objects
            .select_related("site__customer", "order")
            .prefetch_related("assignments__technician", "schedule_changes"))


def is_office(user):
    """Anyone who may see the whole diary rather than their own row of it."""
    return user.has_any_role(Role.OPERATIONS_MANAGER, Role.SALES,
                             Role.SUPPORT, Role.DIRECTOR)


class JobListView(generics.ListAPIView):
    permission_classes = [SchedulingAccess]

    def get_serializer_class(self):
        return JobSerializer if is_office(self.request.user) else TechnicianJobSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = jobs_with_detail()
        params = self.request.query_params

        # A technician is never shown somebody else's visit.
        if not is_office(user):
            queryset = queryset.filter(assignments__technician=user)
        elif params.get("mine") == "true":
            queryset = queryset.filter(assignments__technician=user)

        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("kind"):
            queryset = queryset.filter(kind=params["kind"])
        if params.get("from"):
            queryset = queryset.filter(starts_at__gte=params["from"])
        if params.get("to"):
            queryset = queryset.filter(starts_at__lte=params["to"])
        if params.get("blocked") == "true":
            queryset = queryset.exclude(blocked_reason="")
        return queryset.distinct()


class JobDetailView(generics.RetrieveAPIView):
    permission_classes = [SchedulingAccess]

    def get_serializer_class(self):
        return JobSerializer if is_office(self.request.user) else TechnicianJobSerializer

    def get_queryset(self):
        queryset = jobs_with_detail()
        if not is_office(self.request.user):
            queryset = queryset.filter(assignments__technician=self.request.user)
        return queryset


class JobCreateView(APIView):
    permission_classes = [SchedulingAccess]

    def post(self, request):
        serializer = JobCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = create_job(serializer.validated_data, request.user)
        return Response(JobSerializer(jobs_with_detail().get(pk=job.pk)).data, status=201)


class JobActionView(APIView):
    """One place for the four state changes, so they share their plumbing."""

    permission_classes = [SchedulingAccess]

    SERIALIZERS = {
        "reschedule": RescheduleSerializer,
        "block": BlockSerializer,
        "start": RevisionSerializer,
        "cancel": RevisionSerializer,
    }
    HANDLERS = {
        "reschedule": reschedule_job,
        "block": block_job,
        "start": start_job,
        "cancel": cancel_job,
    }

    def post(self, request, pk, action):
        if action not in self.HANDLERS:
            return Response({"action": ["Unknown job action."]}, status=400)

        serializer = self.SERIALIZERS[action](data=request.data)
        serializer.is_valid(raise_exception=True)
        self.HANDLERS[action](pk, serializer.validated_data, request.user)
        return Response(JobSerializer(jobs_with_detail().get(pk=pk)).data)
