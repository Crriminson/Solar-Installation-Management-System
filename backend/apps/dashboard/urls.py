"""Director dashboard routes under the versioned API."""

from django.urls import path

from .views import DashboardView, MetricCsvView, MetricRowsView, SummaryPdfView

urlpatterns = [
    path("dashboard/", DashboardView.as_view(), name="dashboard"),
    path("dashboard/metrics/<str:key>/", MetricRowsView.as_view(), name="dashboard-metric"),
    path("dashboard/export/summary.pdf", SummaryPdfView.as_view(), name="dashboard-pdf"),
    path("dashboard/export/<str:key>.csv", MetricCsvView.as_view(), name="dashboard-csv"),
]
