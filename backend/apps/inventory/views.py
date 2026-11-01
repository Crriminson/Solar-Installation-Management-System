"""
Purchasing and stock endpoints (F08).

    GET/POST /api/v1/suppliers/                   suppliers
    GET/POST /api/v1/purchase-orders/             purchase orders
    GET      /api/v1/purchase-orders/<id>/        one, with its lines
    POST     /api/v1/purchase-orders/<id>/place/  send to the supplier
    POST     /api/v1/purchase-orders/<id>/cancel/ cancel
    POST     /api/v1/purchase-orders/<id>/receive/ book in what arrived
    GET      /api/v1/stock/units/                 serialized units
    GET      /api/v1/stock/lots/                  batch lots
    GET      /api/v1/stock/movements/             the full stock history
    GET      /api/v1/stock/labels/?purchase_order= barcode labels as received
    GET      /api/v1/stock/labels/?order=          barcode labels for an order's goods

Purchasing is the warehouse's and the operations manager's. Costs are
visible here, so Sales is not given access (D039).
"""

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404
from rest_framework import generics
from rest_framework import serializers
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.catalogue.models import Product
from apps.core.api import StaffAccess
from apps.orders.models import Order

from .labels import labels_for_order, labels_for_purchase, labels_pdf
from .models import (BatchLot, PurchaseOrder, PurchaseOrderLine, SerializedUnit,
                     StockMovement, Supplier)
from .serializers import (BatchLotSerializer, GoodsReceiptSerializer,
                          PurchaseOrderCreateSerializer, PurchaseOrderSerializer,
                          ReceiveSerializer, SerializedUnitSerializer,
                          StockMovementSerializer, SupplierSerializer)
from .services import cancel_purchase_order, place_purchase_order, receive_goods


class WarehouseAccess(StaffAccess):
    """Acquisition cost is on these records, so Sales stays out (D039)."""

    def has_permission(self, request, view):
        view.read_roles = (Role.WAREHOUSE, Role.OPERATIONS_MANAGER, Role.FINANCE,
                           Role.DIRECTOR)
        view.write_roles = (Role.WAREHOUSE, Role.OPERATIONS_MANAGER)
        return super().has_permission(request, view)


# ============================================================
# Suppliers
# ============================================================

class SupplierListView(generics.ListCreateAPIView):
    permission_classes = [WarehouseAccess]
    serializer_class = SupplierSerializer

    def get_queryset(self):
        queryset = Supplier.objects.all()
        if self.request.query_params.get("active") == "true":
            queryset = queryset.filter(is_active=True)
        return queryset


class SupplierDetailView(generics.RetrieveUpdateAPIView):
    permission_classes = [WarehouseAccess]
    serializer_class = SupplierSerializer
    queryset = Supplier.objects.all()


# ============================================================
# Purchase orders
# ============================================================

def purchases_with_lines():
    return (PurchaseOrder.objects
            .select_related("supplier")
            .prefetch_related("lines__product"))


class PurchaseOrderListView(generics.ListAPIView):
    permission_classes = [WarehouseAccess]
    serializer_class = PurchaseOrderSerializer

    def get_queryset(self):
        queryset = purchases_with_lines()
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(reference__icontains=search) | Q(supplier__name__icontains=search)
            )
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        return queryset


class PurchaseOrderDetailView(generics.RetrieveAPIView):
    permission_classes = [WarehouseAccess]
    serializer_class = PurchaseOrderSerializer
    queryset = purchases_with_lines()


class PurchaseOrderCreateView(APIView):
    permission_classes = [WarehouseAccess]

    @transaction.atomic
    def post(self, request):
        serializer = PurchaseOrderCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        supplier = Supplier.objects.filter(pk=data["supplier"], is_active=True).first()
        if supplier is None:
            return Response({"supplier": ["No active supplier with that id."]}, status=400)

        purchase = PurchaseOrder.objects.create(
            supplier=supplier,
            raised_by=request.user,
            expected_on=data.get("expected_on"),
            supplier_invoice_reference=data.get("supplier_invoice_reference", "").strip(),
            supplier_invoice_amount=data.get("supplier_invoice_amount"),
        )

        for row in data["lines"]:
            product = Product.objects.filter(pk=row["product"]).first()
            if product is None:
                return Response({"lines": [f"No product with id {row['product']}."]},
                                status=400)
            PurchaseOrderLine.objects.create(
                purchase_order=purchase, product=product,
                quantity=row["quantity"], unit_cost=row["unit_cost"],
            )

        purchase = purchases_with_lines().get(pk=purchase.pk)
        return Response(PurchaseOrderSerializer(purchase).data, status=201)


class PurchaseOrderPlaceView(APIView):
    permission_classes = [WarehouseAccess]

    def post(self, request, pk):
        place_purchase_order(pk, request.data, request.user)
        return Response(PurchaseOrderSerializer(purchases_with_lines().get(pk=pk)).data)


class PurchaseOrderCancelView(APIView):
    permission_classes = [WarehouseAccess]

    def post(self, request, pk):
        cancel_purchase_order(pk, request.data, request.user)
        return Response(PurchaseOrderSerializer(purchases_with_lines().get(pk=pk)).data)


class PurchaseOrderReceiveView(APIView):
    permission_classes = [WarehouseAccess]

    def post(self, request, pk):
        serializer = ReceiveSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        receipt = receive_goods(pk, serializer.validated_data, request.user)
        return Response(GoodsReceiptSerializer(receipt).data, status=201)


# ============================================================
# Stock
# ============================================================

class SerializedUnitListView(generics.ListAPIView):
    """Find a unit by serial or asset id. This is the F13 lookup in embryo."""

    permission_classes = [WarehouseAccess]
    serializer_class = SerializedUnitSerializer

    def get_queryset(self):
        queryset = SerializedUnit.objects.select_related("product")
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(serial_number__icontains=search) | Q(asset_id__icontains=search)
            )
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("product"):
            queryset = queryset.filter(product_id=params["product"])
        if params.get("order"):
            queryset = queryset.filter(order_id=params["order"])
        return queryset


class BatchLotListView(generics.ListAPIView):
    permission_classes = [WarehouseAccess]
    serializer_class = BatchLotSerializer

    def get_queryset(self):
        queryset = BatchLot.objects.select_related("product")
        params = self.request.query_params

        search = params.get("search", "").strip()
        if search:
            queryset = queryset.filter(batch_id__icontains=search)
        if params.get("status"):
            queryset = queryset.filter(status=params["status"])
        if params.get("product"):
            queryset = queryset.filter(product_id=params["product"])
        return queryset


class StockMovementListView(generics.ListAPIView):
    """Why the count is what it is."""

    permission_classes = [WarehouseAccess]
    serializer_class = StockMovementSerializer

    def get_queryset(self):
        queryset = StockMovement.objects.select_related("unit", "lot", "moved_by")
        params = self.request.query_params

        if params.get("unit"):
            queryset = queryset.filter(unit_id=params["unit"])
        if params.get("lot"):
            queryset = queryset.filter(lot_id=params["lot"])
        if params.get("order"):
            queryset = queryset.filter(order_id=params["order"])
        return queryset


class StockLabelsView(APIView):
    """
    Barcode labels for the goods on one purchase order or one customer order.

    By purchase order: every unit and batch as it was received, for
    labelling stock when it arrives. By order: what is held for that
    customer, for the packing bench. One of the two is required, so a
    request never prints the whole warehouse.
    """

    permission_classes = [WarehouseAccess]

    def get(self, request):
        purchase_id = request.query_params.get("purchase_order")
        order_id = request.query_params.get("order")
        if bool(purchase_id) == bool(order_id):
            raise ValidationError({"detail": ["Choose a purchase order or an order to label."]})

        target_id = serializers.IntegerField(min_value=1).run_validation(purchase_id or order_id)

        if purchase_id:
            purchase = get_object_or_404(PurchaseOrder, pk=target_id)
            labels, name = labels_for_purchase(purchase), purchase.reference
        else:
            order = get_object_or_404(Order, pk=target_id)
            labels, name = labels_for_order(order), order.reference

        response = HttpResponse(labels_pdf(labels, f"Stock labels {name}"),
                                content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="labels-{name}.pdf"'
        return response
