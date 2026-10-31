"""
Support endpoints (F13).

    GET  /api/v1/support/lookup/?q=             find by name, phone, order or serial
    GET  /api/v1/support/customers/<id>/        a customer's equipment and cover
    GET  /api/v1/tickets/                       the ticket queue
    POST /api/v1/tickets/raise/                 open a ticket
    GET  /api/v1/tickets/<id>/                  one ticket
    POST /api/v1/tickets/<id>/photos/           attach captioned evidence
    POST /api/v1/tickets/<id>/<action>/         every other state change

Support and operations run tickets. A technician reaches only tickets
they have a visit on, and only the actions a visit involves. Finance and
the director read. Sales has no ticket access (rules.md section 4).
"""

from django.conf import settings
from django.db.models import Q
from rest_framework import generics
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.parsers import FormParser, MultiPartParser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import StaffAccess
from apps.customers.models import Customer
from apps.inventory.models import SerializedUnit, StockStatus
from apps.scheduling.serializers import JobSerializer
from apps.warranties.models import AssetWarranty
from apps.warranties.serializers import WarrantySerializer

from . import services
from .models import ServiceTicket, TicketPhoto, TicketStatus
from .serializers import (AssignSerializer, BlockSerializer, ConfirmSerializer,
                          DecideEstimateSerializer, DiagnoseSerializer, EstimateSerializer,
                          PhotoInputSerializer, RaiseSerializer, ReplaceSerializer,
                          RevisionSerializer, ReviewSerializer, TicketDetailSerializer,
                          TicketListSerializer, TicketPhotoSerializer, VisitSerializer,
                          VoidLineSerializer, WorkLineInputSerializer)

LOOKUP_MINIMUM_LENGTH = 2
LOOKUP_ROW_LIMIT = 20

# Action name to (input contract, service).
ACTIONS = {
    "assign": (AssignSerializer, services.assign_ticket),
    "block": (BlockSerializer, services.block_ticket),
    "unblock": (RevisionSerializer, services.unblock_ticket),
    "diagnose": (DiagnoseSerializer, services.diagnose),
    "estimate": (EstimateSerializer, services.create_estimate),
    "decide-estimate": (DecideEstimateSerializer, services.decide_estimate),
    "start-work": (RevisionSerializer, services.start_work),
    "work-line": (WorkLineInputSerializer, services.add_work_line),
    "void-line": (VoidLineSerializer, services.void_work_line),
    "replace": (ReplaceSerializer, services.replace_unit),
    "finish": (RevisionSerializer, services.finish_work),
    "confirm": (ConfirmSerializer, services.confirm_resolution),
    "send-back": (RevisionSerializer, services.send_back),
    "reopen": (RevisionSerializer, services.reopen_ticket),
}

# What a visit involves. Pricing, approvals and closing stay with the office.
TECHNICIAN_ACTIONS = {"diagnose", "start-work", "work-line", "void-line", "replace", "finish"}

# Only these may decide a disputed claim (spec.md F13).
REVIEW_ROLES = (Role.OPERATIONS_MANAGER,)


class TicketAccess(StaffAccess):
    def has_permission(self, request, view):
        view.read_roles = (Role.SUPPORT, Role.OPERATIONS_MANAGER, Role.TECHNICIAN,
                           Role.FINANCE, Role.DIRECTOR)
        view.write_roles = (Role.SUPPORT, Role.OPERATIONS_MANAGER, Role.TECHNICIAN)
        return super().has_permission(request, view)


class OfficeAccess(StaffAccess):
    """Customer lookup, which a technician's assignments do not extend to."""

    def has_permission(self, request, view):
        view.read_roles = (Role.SUPPORT, Role.OPERATIONS_MANAGER, Role.DIRECTOR)
        view.write_roles = (Role.SUPPORT, Role.OPERATIONS_MANAGER)
        return super().has_permission(request, view)


def sees_all_tickets(user):
    return user.has_any_role(Role.SUPPORT, Role.OPERATIONS_MANAGER, Role.FINANCE, Role.DIRECTOR)


def tickets_for(user):
    """A technician sees the tickets they have a visit on, and no others."""
    queryset = ServiceTicket.objects.select_related("customer", "site", "order", "owner")
    if sees_all_tickets(user):
        return queryset
    return queryset.filter(jobs__assignments__technician=user).distinct()


def with_detail(queryset):
    return queryset.prefetch_related(
        "assets__unit__product", "assets__warranty__replaced_by", "assets__replacement",
        "estimates__lines", "work_lines__invoice", "photos", "jobs__assignments__technician",
        "replacements__old_unit", "replacements__new_unit",
    )


def ticket_detail(ticket_id, request):
    ticket = with_detail(tickets_for(request.user)).filter(pk=ticket_id).first()
    if ticket is None:
        raise NotFound()
    return TicketDetailSerializer(ticket, context={"request": request}).data


# ============================================================
# Lookup
# ============================================================

class LookupView(APIView):
    """The phone rings; whatever the caller has to hand finds them."""

    permission_classes = [OfficeAccess]

    def get(self, request):
        term = request.query_params.get("q", "").strip()
        if len(term) < LOOKUP_MINIMUM_LENGTH:
            return Response({"customers": [], "assets": []})

        customers = Customer.objects.filter(
            Q(full_name__icontains=term) | Q(phone__icontains=term)
            | Q(order__reference__icontains=term)
        ).distinct()[:LOOKUP_ROW_LIMIT]

        warranties = (AssetWarranty.objects
                      .select_related("unit__product", "customer", "site", "order", "replaced_by")
                      .filter(Q(unit__serial_number__icontains=term)
                              | Q(unit__asset_id__icontains=term))[:LOOKUP_ROW_LIMIT])

        return Response({
            "customers": [{"id": customer.pk, "name": customer.full_name, "phone": customer.phone}
                          for customer in customers],
            "assets": WarrantySerializer(warranties, many=True).data,
        })


class CustomerEquipmentView(APIView):
    """A customer's units, with cover shown beside each, to raise a ticket from."""

    permission_classes = [OfficeAccess]

    def get(self, request, pk):
        customer = Customer.objects.filter(pk=pk).first()
        if customer is None:
            raise NotFound()

        units = (SerializedUnit.objects
                 .filter(customer=customer,
                         status__in=[StockStatus.DELIVERED, StockStatus.INSTALLED])
                 .select_related("product", "order", "site").order_by("id"))
        warranties = {}
        for warranty in (AssetWarranty.objects.filter(customer=customer)
                         .select_related("unit__product", "customer", "site", "order",
                                         "replaced_by").order_by("id")):
            warranties[warranty.unit_id] = warranty

        return Response({
            "id": customer.pk, "name": customer.full_name, "phone": customer.phone,
            "units": [{
                "id": unit.pk, "asset_id": unit.asset_id, "serial_number": unit.serial_number,
                "sku": unit.product.sku, "product_name": unit.product.name,
                "order_reference": unit.order.reference if unit.order else "",
                "warranty": (WarrantySerializer(warranties[unit.pk]).data
                             if unit.pk in warranties else None),
            } for unit in units],
        })


# ============================================================
# Tickets
# ============================================================

class TicketListView(generics.ListAPIView):
    permission_classes = [TicketAccess]
    serializer_class = TicketListSerializer

    def get_queryset(self):
        queryset = tickets_for(self.request.user).prefetch_related("assets")
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(reference__icontains=search) | Q(customer__full_name__icontains=search)
                | Q(customer__phone__icontains=search) | Q(order__reference__icontains=search)
                | Q(assets__unit__serial_number__icontains=search)
                | Q(assets__unit__asset_id__icontains=search)
            ).distinct()
        if params.get("status") in TicketStatus.values:
            queryset = queryset.filter(status=params["status"])
        if params.get("open") == "true":
            queryset = queryset.exclude(status=TicketStatus.CLOSED)
        if params.get("unassigned") == "true":
            queryset = queryset.filter(owner__isnull=True).exclude(status=TicketStatus.CLOSED)
        if params.get("priority"):
            queryset = queryset.filter(priority=params["priority"])
        return queryset


class TicketDetailView(APIView):
    permission_classes = [TicketAccess]

    def get(self, request, pk):
        return Response(ticket_detail(pk, request))


class TicketRaiseView(APIView):
    permission_classes = [TicketAccess]

    def post(self, request):
        if not services.is_office(request.user):
            raise PermissionDenied("Tickets are raised by support.")

        serializer = RaiseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ticket = services.raise_ticket(serializer.validated_data, request.user)
        return Response(ticket_detail(ticket.pk, request), status=201)


class TicketReviewView(APIView):
    """Separate from the other actions: support may not rule on its own claims."""

    permission_classes = [TicketAccess]

    def post(self, request, pk):
        if not request.user.has_any_role(*REVIEW_ROLES):
            raise PermissionDenied("Only an operations manager may review a claim.")

        serializer = ReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.review_assessment(pk, serializer.validated_data, request.user)
        return Response(ticket_detail(pk, request))


class TicketVisitView(APIView):
    permission_classes = [TicketAccess]

    def post(self, request, pk):
        if not services.is_office(request.user):
            raise PermissionDenied("Visits are booked by the office.")

        serializer = VisitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        job = services.book_visit(pk, serializer.validated_data, request.user)
        return Response(JobSerializer(job).data, status=201)


class TicketActionView(APIView):
    permission_classes = [TicketAccess]

    def post(self, request, pk, action):
        if action not in ACTIONS:
            return Response({"action": ["Unknown ticket action."]}, status=400)

        if not services.is_office(request.user):
            if action not in TECHNICIAN_ACTIONS:
                raise PermissionDenied("That action belongs to the office.")
            if not tickets_for(request.user).filter(pk=pk).exists():
                raise NotFound()

        contract, handler = ACTIONS[action]
        serializer = contract(data=request.data)
        serializer.is_valid(raise_exception=True)
        handler(pk, serializer.validated_data, request.user)
        return Response(ticket_detail(pk, request))


class TicketPhotoView(APIView):
    permission_classes = [TicketAccess]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, pk):
        ticket = tickets_for(request.user).filter(pk=pk).first()
        if ticket is None:
            raise NotFound()
        if ticket.photos.count() >= settings.MAX_PHOTOS_PER_RECORD:
            return Response({"image": ["This ticket has all the photos it can take."]}, status=400)

        serializer = PhotoInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        photo = TicketPhoto.objects.create(
            ticket=ticket, uploaded_by=request.user, **serializer.validated_data
        )
        return Response(TicketPhotoSerializer(photo).data, status=201)
