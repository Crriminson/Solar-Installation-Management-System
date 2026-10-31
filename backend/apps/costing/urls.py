"""Cost and payable routes under the versioned API."""

from django.urls import path

from .views import (ExpenseView, JobCostView, RateView, ReverseExpenseView,
                    ReverseSupplierPaymentView, ReverseTechnicianPaymentView, ReverseTimeView,
                    SupplierInvoiceView, SupplierPaymentView, TechnicianPaymentView,
                    TechnicianSummaryView, TimeEntryView)

urlpatterns = [
    path("costing/orders/<int:pk>/", JobCostView.as_view(), name="job-cost"),
    path("costing/technicians/", TechnicianSummaryView.as_view(), name="technician-summary"),
    path("costing/rates/", RateView.as_view(), name="technician-rates"),
    path("costing/time/", TimeEntryView.as_view(), name="time-entries"),
    path("costing/time/<int:pk>/reverse/", ReverseTimeView.as_view(), name="time-reverse"),
    path("costing/technician-payments/", TechnicianPaymentView.as_view(),
         name="technician-payments"),
    path("costing/technician-payments/<int:pk>/reverse/", ReverseTechnicianPaymentView.as_view(),
         name="technician-payment-reverse"),
    path("costing/expenses/", ExpenseView.as_view(), name="expenses"),
    path("costing/expenses/<int:pk>/reverse/", ReverseExpenseView.as_view(), name="expense-reverse"),
    path("costing/supplier-payments/", SupplierPaymentView.as_view(), name="supplier-payments"),
    path("costing/supplier-payments/<int:pk>/reverse/", ReverseSupplierPaymentView.as_view(),
         name="supplier-payment-reverse"),
    path("costing/purchases/<int:pk>/invoice/", SupplierInvoiceView.as_view(),
         name="supplier-invoice"),
]
