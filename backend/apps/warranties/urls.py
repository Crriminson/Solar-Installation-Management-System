"""Warranty routes under the versioned API."""

from django.urls import path

from .views import OrderWarrantiesView, WarrantyDetailView, WarrantyListView

urlpatterns = [
    path("warranties/", WarrantyListView.as_view(), name="warranty-list"),
    path("warranties/<int:pk>/", WarrantyDetailView.as_view(), name="warranty-detail"),
    path("orders/<int:pk>/warranties/", OrderWarrantiesView.as_view(), name="order-warranties"),
]
