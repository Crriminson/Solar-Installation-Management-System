"""Warehouse fulfilment routes under the versioned API."""

from django.urls import path

from .views import (FulfilmentCloseView, FulfilmentDeliverView, FulfilmentDetailView,
                    FulfilmentDispatchView, FulfilmentListView, FulfilmentOpenView,
                    FulfilmentReserveView, FulfilmentScanView)

urlpatterns = [
    path("fulfilments/", FulfilmentListView.as_view(), name="fulfilment-list"),
    path("fulfilments/open/", FulfilmentOpenView.as_view(), name="fulfilment-open"),
    path("fulfilments/<int:pk>/", FulfilmentDetailView.as_view(), name="fulfilment-detail"),
    path("fulfilments/<int:pk>/reserve/", FulfilmentReserveView.as_view(), name="fulfilment-reserve"),
    path("fulfilments/<int:pk>/scan/", FulfilmentScanView.as_view(), name="fulfilment-scan"),
    path("fulfilments/<int:pk>/close/", FulfilmentCloseView.as_view(), name="fulfilment-close"),
    path("fulfilments/<int:pk>/dispatch/", FulfilmentDispatchView.as_view(), name="fulfilment-dispatch"),
    path("fulfilments/<int:pk>/deliver/", FulfilmentDeliverView.as_view(), name="fulfilment-deliver"),
]
