"""Order and payment routes under the versioned API."""

from django.urls import path

from .views import (BalanceInvoiceView, OrderCancelView, OrderConfirmView, OrderDetailView,
                    OrderListView, PaymentAllocateView, PaymentClearView, PaymentCreateView,
                    PaymentReverseView)

urlpatterns = [
    path("orders/", OrderListView.as_view(), name="order-list"),
    path("orders/confirm/", OrderConfirmView.as_view(), name="order-confirm"),
    path("orders/<int:pk>/", OrderDetailView.as_view(), name="order-detail"),
    path("orders/<int:pk>/cancel/", OrderCancelView.as_view(), name="order-cancel"),
    path("orders/<int:pk>/balance-invoice/", BalanceInvoiceView.as_view(),
         name="order-balance-invoice"),
    path("orders/<int:pk>/payments/", PaymentCreateView.as_view(), name="payment-create"),

    path("payments/<int:pk>/clear/", PaymentClearView.as_view(), name="payment-clear"),
    path("payments/<int:pk>/reverse/", PaymentReverseView.as_view(), name="payment-reverse"),
    path("payments/<int:pk>/allocate/", PaymentAllocateView.as_view(), name="payment-allocate"),
]
