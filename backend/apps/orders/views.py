"""
Order and money endpoints (F07).

    GET  /api/v1/orders/                        list
    GET  /api/v1/orders/<id>/                   one order with its money
    POST /api/v1/orders/confirm/                accepted quotation -> order
    POST /api/v1/orders/<id>/cancel/            cancel, with a reason
    POST /api/v1/orders/<id>/balance-invoice/   raise the balance
    POST /api/v1/orders/<id>/payments/          record money that moved
    POST /api/v1/payments/<id>/clear/           confirm it arrived
    POST /api/v1/payments/<id>/reverse/         undo a mis-entry
    POST /api/v1/payments/<id>/allocate/        point it at an invoice

Recording money is Finance's job, not Sales'. Confirming the order is
Sales', because it follows their acceptance.
"""

from django.db.models import Prefetch, Q
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import StaffAccess

from .models import Order, Payment
from .serializers import (AllocateSerializer, ConfirmSerializer, OrderSerializer,
                          PaymentCreateSerializer, PaymentSerializer, RevisionSerializer)
from .services import (allocate_payment, cancel_order, clear_payment, confirm_order,
                       issue_balance_invoice, record_payment, reverse_payment)


class OrderAccess(StaffAccess):
    """Sales confirm and cancel; everyone operational may read."""

    def has_permission(self, request, view):
        view.read_roles = (Role.SALES, Role.OPERATIONS_MANAGER, Role.FINANCE,
                           Role.WAREHOUSE, Role.DIRECTOR)
        view.write_roles = (Role.SALES, Role.OPERATIONS_MANAGER)
        return super().has_permission(request, view)


class MoneyAccess(StaffAccess):
    """Only Finance and administrators touch the ledger."""

    def has_permission(self, request, view):
        view.read_roles = (Role.FINANCE, Role.OPERATIONS_MANAGER, Role.DIRECTOR, Role.SALES)
        view.write_roles = (Role.FINANCE,)
        return super().has_permission(request, view)


def orders_with_money():
    from apps.scheduling.models import Job, JobKind, JobStatus

    installations = Job.objects.filter(kind=JobKind.INSTALLATION).exclude(
        status=JobStatus.CANCELLED)
    return (Order.objects
            .select_related("quotation__quote", "customer", "site", "fulfilment")
            .prefetch_related("invoices", "payments__allocations__invoice",
                              Prefetch("jobs", queryset=installations,
                                       to_attr="installation_jobs")))


class OrderListView(generics.ListAPIView):
    permission_classes = [OrderAccess]
    serializer_class = OrderSerializer

    def get_queryset(self):
        queryset = orders_with_money()
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(reference__icontains=search) | Q(customer__full_name__icontains=search)
            )
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("awaiting_payment") == "true":
            queryset = queryset.filter(status="confirmed")
        return queryset


class OrderDetailView(generics.RetrieveAPIView):
    permission_classes = [OrderAccess]
    serializer_class = OrderSerializer
    queryset = orders_with_money()


class OrderConfirmView(APIView):
    permission_classes = [OrderAccess]

    def post(self, request):
        serializer = ConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = confirm_order(serializer.validated_data["quotation"], request.user)
        return Response(OrderSerializer(orders_with_money().get(pk=order.pk)).data, status=201)


class OrderCancelView(APIView):
    permission_classes = [OrderAccess]

    def post(self, request, pk):
        serializer = RevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cancel_order(pk, serializer.validated_data, request.user)
        return Response(OrderSerializer(orders_with_money().get(pk=pk)).data)


class BalanceInvoiceView(APIView):
    permission_classes = [MoneyAccess]

    def post(self, request, pk):
        issue_balance_invoice(pk, request.user)
        order = orders_with_money().get(pk=pk)
        return Response(OrderSerializer(order).data, status=201)


class PaymentCreateView(APIView):
    permission_classes = [MoneyAccess]

    def post(self, request, pk):
        serializer = PaymentCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = record_payment(pk, serializer.validated_data, request.user)
        return Response(PaymentSerializer(payment).data, status=201)


class PaymentClearView(APIView):
    permission_classes = [MoneyAccess]

    def post(self, request, pk):
        serializer = RevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = clear_payment(pk, serializer.validated_data, request.user)
        return Response(PaymentSerializer(payment).data)


class PaymentReverseView(APIView):
    permission_classes = [MoneyAccess]

    def post(self, request, pk):
        serializer = RevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = reverse_payment(pk, serializer.validated_data, request.user)
        return Response(PaymentSerializer(payment).data)


class PaymentAllocateView(APIView):
    permission_classes = [MoneyAccess]

    def post(self, request, pk):
        serializer = AllocateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payment = allocate_payment(pk, serializer.validated_data, request.user)
        return Response(PaymentSerializer(payment).data)
