"""
Warehouse fulfilment endpoints (F09).

    GET  /api/v1/fulfilments/                   list
    GET  /api/v1/fulfilments/<id>/              one, with its checklist
    POST /api/v1/fulfilments/open/              build the checklist
    POST /api/v1/fulfilments/<id>/reserve/      claim the stock
    POST /api/v1/fulfilments/<id>/scan/         confirm one item
    POST /api/v1/fulfilments/<id>/close/        seal the box
    POST /api/v1/fulfilments/<id>/dispatch/     send it out
    POST /api/v1/fulfilments/<id>/deliver/      record arrival
"""

from django.db.models import Q
from rest_framework import generics
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import StaffAccess

from .models import Fulfilment
from .serializers import (DeliverSerializer, DispatchSerializer, FulfilmentSerializer,
                          RevisionSerializer, ScanEventSerializer, ScanSerializer)
from .services import (close_packing, deliver, dispatch, open_fulfilment, reserve_stock,
                       scan_item)


class FulfilmentAccess(StaffAccess):
    """The warehouse packs; sales and finance watch."""

    def has_permission(self, request, view):
        view.read_roles = (Role.WAREHOUSE, Role.OPERATIONS_MANAGER, Role.SALES,
                           Role.FINANCE, Role.DIRECTOR)
        view.write_roles = (Role.WAREHOUSE, Role.OPERATIONS_MANAGER)
        return super().has_permission(request, view)


def fulfilments_with_lines():
    return (Fulfilment.objects
            .select_related("order__customer", "order__quotation")
            .prefetch_related("lines__scans__unit", "lines__scans__lot"))


class FulfilmentListView(generics.ListAPIView):
    permission_classes = [FulfilmentAccess]
    serializer_class = FulfilmentSerializer

    def get_queryset(self):
        queryset = fulfilments_with_lines()
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(order__reference__icontains=search)
                | Q(order__customer__full_name__icontains=search)
            )
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("to_pack") == "true":
            queryset = queryset.filter(status__in=["pending", "reserved", "blocked"])
        return queryset


class FulfilmentDetailView(generics.RetrieveAPIView):
    permission_classes = [FulfilmentAccess]
    serializer_class = FulfilmentSerializer
    queryset = fulfilments_with_lines()


class FulfilmentOpenView(APIView):
    permission_classes = [FulfilmentAccess]

    def post(self, request):
        order_id = request.data.get("order")
        fulfilment = open_fulfilment(order_id, request.user)
        return Response(
            FulfilmentSerializer(fulfilments_with_lines().get(pk=fulfilment.pk)).data,
            status=201,
        )


class FulfilmentReserveView(APIView):
    permission_classes = [FulfilmentAccess]

    def post(self, request, pk):
        reserve_stock(pk, request.user)
        return Response(FulfilmentSerializer(fulfilments_with_lines().get(pk=pk)).data)


class FulfilmentScanView(APIView):
    permission_classes = [FulfilmentAccess]

    def post(self, request, pk):
        serializer = ScanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        scan = scan_item(pk, serializer.validated_data, request.user)
        return Response(ScanEventSerializer(scan).data, status=201)


class FulfilmentCloseView(APIView):
    permission_classes = [FulfilmentAccess]

    def post(self, request, pk):
        serializer = RevisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        close_packing(pk, serializer.validated_data, request.user)
        return Response(FulfilmentSerializer(fulfilments_with_lines().get(pk=pk)).data)


class FulfilmentDispatchView(APIView):
    permission_classes = [FulfilmentAccess]

    def post(self, request, pk):
        serializer = DispatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dispatch(pk, serializer.validated_data, request.user)
        return Response(FulfilmentSerializer(fulfilments_with_lines().get(pk=pk)).data)


class FulfilmentDeliverView(APIView):
    permission_classes = [FulfilmentAccess]

    def post(self, request, pk):
        serializer = DeliverSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        deliver(pk, serializer.validated_data, request.user)
        return Response(FulfilmentSerializer(fulfilments_with_lines().get(pk=pk)).data)
