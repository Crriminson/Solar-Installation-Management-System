"""Purchasing and stock routes under the versioned API."""

from django.urls import path

from .views import (BatchLotListView, PurchaseOrderCancelView, PurchaseOrderCreateView,
                    PurchaseOrderDetailView, PurchaseOrderListView, PurchaseOrderPlaceView,
                    PurchaseOrderReceiveView, SerializedUnitListView, StockLabelsView,
                    StockMovementListView, SupplierDetailView, SupplierListView)

urlpatterns = [
    path("suppliers/", SupplierListView.as_view(), name="supplier-list"),
    path("suppliers/<int:pk>/", SupplierDetailView.as_view(), name="supplier-detail"),

    path("purchase-orders/", PurchaseOrderListView.as_view(), name="purchase-list"),
    path("purchase-orders/create/", PurchaseOrderCreateView.as_view(), name="purchase-create"),
    path("purchase-orders/<int:pk>/", PurchaseOrderDetailView.as_view(), name="purchase-detail"),
    path("purchase-orders/<int:pk>/place/", PurchaseOrderPlaceView.as_view(), name="purchase-place"),
    path("purchase-orders/<int:pk>/cancel/", PurchaseOrderCancelView.as_view(), name="purchase-cancel"),
    path("purchase-orders/<int:pk>/receive/", PurchaseOrderReceiveView.as_view(), name="purchase-receive"),

    path("stock/units/", SerializedUnitListView.as_view(), name="stock-units"),
    path("stock/lots/", BatchLotListView.as_view(), name="stock-lots"),
    path("stock/movements/", StockMovementListView.as_view(), name="stock-movements"),
    path("stock/labels/", StockLabelsView.as_view(), name="stock-labels"),
]
