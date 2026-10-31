"""
Warranty lookup endpoints (F12).

    GET /api/v1/warranties/                  list, search and filter
    GET /api/v1/warranties/<id>/             one, with its replacement history
    GET /api/v1/orders/<id>/warranties/      an order's cover, and any gaps in it

Read-only. A warranty is created by a delivery or a replacement, never
by a form, and no role may write here.

Technicians are left out: they reach their own assignments only, and
F13 decides what a service visit needs to see.
"""

from django.db.models import Q
from rest_framework import generics
from rest_framework.exceptions import NotFound
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.core.api import StaffAccess, business_date
from apps.inventory.models import SerializedUnit, StockStatus
from apps.orders.models import Order

from .models import AssetWarranty, WarrantyStatus
from .serializers import (UncoveredUnitSerializer, WarrantyDetailSerializer,
                          WarrantyFilterSerializer, WarrantySerializer)


class WarrantyAccess(StaffAccess):
    """Everyone who already sees the order may look up its cover."""

    def has_permission(self, request, view):
        view.read_roles = (Role.SUPPORT, Role.OPERATIONS_MANAGER, Role.SALES,
                           Role.WAREHOUSE, Role.FINANCE, Role.DIRECTOR)
        view.write_roles = ()
        return super().has_permission(request, view)


def warranties_with_parties():
    return (AssetWarranty.objects
            .select_related("unit__product", "customer", "site", "order", "replaced_by"))


def _with_status(queryset, status):
    """Status is never stored, so each one is a question about today."""
    today = business_date()
    return {
        WarrantyStatus.IN_COVER: lambda: queryset.in_cover(today),
        WarrantyStatus.EXPIRED: lambda: queryset.expired(today),
        WarrantyStatus.REPLACED: queryset.replaced,
    }[status]()


class WarrantyListView(generics.ListAPIView):
    permission_classes = [WarrantyAccess]
    serializer_class = WarrantySerializer

    def get_queryset(self):
        filters = WarrantyFilterSerializer(data=self.request.query_params)
        filters.is_valid(raise_exception=True)
        chosen = filters.validated_data

        queryset = warranties_with_parties()
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(unit__serial_number__icontains=search)
                | Q(unit__asset_id__icontains=search)
                | Q(customer__full_name__icontains=search)
                | Q(customer__phone__icontains=search)
                | Q(order__reference__icontains=search)
            )
        if "status" in chosen:
            queryset = _with_status(queryset, chosen["status"])
        if "order" in chosen:
            queryset = queryset.filter(order_id=chosen["order"])
        if "customer" in chosen:
            queryset = queryset.filter(customer_id=chosen["customer"])
        return queryset


class WarrantyDetailView(generics.RetrieveAPIView):
    permission_classes = [WarrantyAccess]
    serializer_class = WarrantyDetailSerializer
    queryset = warranties_with_parties()


class OrderWarrantiesView(APIView):
    """
    What this order's delivery left covered, and what it did not.

    Unpaginated: the rows are bounded by what fits on one order, and a
    missing unit on a later page would look like a covered one.
    """

    permission_classes = [WarrantyAccess]

    def get(self, request, pk):
        order = Order.objects.filter(pk=pk).first()
        if order is None:
            raise NotFound()

        warranties = warranties_with_parties().filter(order=order).order_by("id")
        uncovered = (SerializedUnit.objects
                     .filter(order=order, status__in=[StockStatus.DELIVERED,
                                                      StockStatus.INSTALLED])
                     .exclude(warranties__order=order)
                     .select_related("product")
                     .order_by("id"))
        return Response({
            "warranties": WarrantySerializer(warranties, many=True).data,
            "uncovered_units": UncoveredUnitSerializer(uncovered, many=True).data,
        })
