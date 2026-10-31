"""
Cost and payable endpoints (F14).

    GET      /api/v1/costing/orders/<id>/            what one job cost
    GET      /api/v1/costing/technicians/            hours and balance per person
    GET/POST /api/v1/costing/rates/                  technician cost rates
    GET/POST /api/v1/costing/time/                   time entries
    POST     /api/v1/costing/time/<id>/reverse/      undo a mis-entry
    GET/POST /api/v1/costing/technician-payments/    pay against the accrual
    POST     /api/v1/costing/technician-payments/<id>/reverse/
    GET/POST /api/v1/costing/expenses/               direct project costs
    POST     /api/v1/costing/expenses/<id>/reverse/
    GET/POST /api/v1/costing/supplier-payments/      pay a supplier's invoice
    POST     /api/v1/costing/supplier-payments/<id>/reverse/
    POST     /api/v1/costing/purchases/<id>/invoice/ record what they billed

Finance owns every money write. Cost figures are restricted to the roles
in rules.md section 4, so Sales and Support are refused outright. A
technician records and reads their own hours and nothing else here.
"""

from rest_framework import generics
from rest_framework.exceptions import NotFound, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.catalogue.permissions import can_view_costs
from apps.core.api import StaffAccess, exact_decimals
from apps.orders.models import Order

from . import services
from .models import (ProjectExpense, SupplierPayment, TechnicianPayment, TechnicianRate,
                     TimeEntry)
from .serializers import (ExpenseInputSerializer, ExpenseSerializer, RateInputSerializer,
                          RateSerializer, ReverseSerializer, SupplierInvoiceInputSerializer,
                          SupplierPaymentInputSerializer, SupplierPaymentSerializer,
                          TechnicianPaymentInputSerializer, TechnicianPaymentSerializer,
                          TimeEntrySerializer, TimeInputSerializer)


class CostAccess(StaffAccess):
    """Who may see cost, and who may move money. D039 and rules.md section 4."""

    def has_permission(self, request, view):
        view.read_roles = (Role.FINANCE, Role.DIRECTOR, Role.OPERATIONS_MANAGER)
        view.write_roles = (Role.FINANCE,)
        return super().has_permission(request, view)


class TimeAccess(StaffAccess):
    """The crew records its own hours; operations can record them for it."""

    def has_permission(self, request, view):
        view.read_roles = (Role.TECHNICIAN, Role.FINANCE, Role.DIRECTOR,
                           Role.OPERATIONS_MANAGER)
        view.write_roles = (Role.TECHNICIAN, Role.OPERATIONS_MANAGER, Role.FINANCE)
        return super().has_permission(request, view)


# ============================================================
# Job cost and technician balances
# ============================================================

class JobCostView(APIView):
    permission_classes = [CostAccess]

    def get(self, request, pk):
        order = Order.objects.select_related("quotation").filter(pk=pk).first()
        if order is None:
            raise NotFound()
        return Response(exact_decimals(services.costs_for_orders([order])[order.pk]))


class TechnicianSummaryView(APIView):
    permission_classes = [CostAccess]

    def get(self, request):
        return Response(exact_decimals(services.technician_summaries()))


# ============================================================
# Ledgers
# ============================================================

class LedgerView(generics.ListAPIView):
    """List a ledger; post through its service. Each subclass only names them."""

    input_serializer = None
    create_service = None
    filter_fields = ()

    def get_queryset(self):
        queryset = self.queryset.all()
        for name in self.filter_fields:
            value = self.request.query_params.get(name, "")
            if value.isdigit():
                queryset = queryset.filter(**{name: value})
        return queryset

    def post(self, request):
        serializer = self.input_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = type(self).create_service(serializer.validated_data, request.user)
        output = self.serializer_class(record, context=self.get_serializer_context())
        return Response(output.data, status=201)


class RateView(LedgerView):
    permission_classes = [CostAccess]
    serializer_class = RateSerializer
    queryset = TechnicianRate.objects.select_related("technician")
    input_serializer = RateInputSerializer
    create_service = services.set_rate
    filter_fields = ("technician",)


class TechnicianPaymentView(LedgerView):
    permission_classes = [CostAccess]
    serializer_class = TechnicianPaymentSerializer
    queryset = TechnicianPayment.objects.select_related("technician")
    input_serializer = TechnicianPaymentInputSerializer
    create_service = services.pay_technician
    filter_fields = ("technician",)


class ExpenseView(LedgerView):
    permission_classes = [CostAccess]
    serializer_class = ExpenseSerializer
    queryset = ProjectExpense.objects.all()
    input_serializer = ExpenseInputSerializer
    create_service = services.record_expense
    filter_fields = ("order",)


class SupplierPaymentView(LedgerView):
    permission_classes = [CostAccess]
    serializer_class = SupplierPaymentSerializer
    queryset = SupplierPayment.objects.select_related("purchase_order")
    input_serializer = SupplierPaymentInputSerializer
    create_service = services.pay_supplier
    filter_fields = ("purchase_order",)


class TimeEntryView(generics.ListAPIView):
    """A technician's own hours, or anyone's for those with cost access."""

    permission_classes = [TimeAccess]
    serializer_class = TimeEntrySerializer

    def get_queryset(self):
        queryset = TimeEntry.objects.select_related("technician")
        user = self.request.user
        if not can_view_costs(user):
            queryset = queryset.filter(technician=user)

        for name in ("job", "technician"):
            value = self.request.query_params.get(name, "")
            if value.isdigit():
                queryset = queryset.filter(**{name: value})
        return queryset

    def post(self, request):
        serializer = TimeInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        if not request.user.has_any_role(Role.OPERATIONS_MANAGER, Role.FINANCE):
            if data.get("technician", request.user.pk) != request.user.pk:
                raise PermissionDenied("You can only record your own hours.")

        entry = services.record_time(data, request.user)
        output = TimeEntrySerializer(entry, context=self.get_serializer_context())
        return Response(output.data, status=201)


# ============================================================
# Reversals and the supplier's invoice
# ============================================================

class ReverseView(APIView):
    """One shape for every reversal. Each route names its record and service."""

    permission_classes = [CostAccess]
    handler = None
    output = None

    def post(self, request, pk):
        serializer = ReverseSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        record = type(self).handler(pk, serializer.validated_data, request.user)
        return Response(self.output(record, context={"request": request}).data)


class ReverseTimeView(ReverseView):
    handler = services.reverse_time
    output = TimeEntrySerializer


class ReverseTechnicianPaymentView(ReverseView):
    handler = services.reverse_technician_payment
    output = TechnicianPaymentSerializer


class ReverseExpenseView(ReverseView):
    handler = services.reverse_expense
    output = ExpenseSerializer


class ReverseSupplierPaymentView(ReverseView):
    handler = services.reverse_supplier_payment
    output = SupplierPaymentSerializer


class SupplierInvoiceView(APIView):
    permission_classes = [CostAccess]

    def post(self, request, pk):
        serializer = SupplierInvoiceInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        purchase = services.record_supplier_invoice(pk, serializer.validated_data, request.user)
        return Response(exact_decimals({
            "id": purchase.pk, "supplier_invoice_reference": purchase.supplier_invoice_reference,
            "supplier_invoice_amount": purchase.supplier_invoice_amount,
        }))
