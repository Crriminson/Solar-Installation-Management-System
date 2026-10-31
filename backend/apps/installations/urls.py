"""Installation evidence routes under the versioned API."""

from django.urls import path

from .views import (InstalledUnitView, PhotoView, ReportDecideView, ReportDetailView,
                    ReportListView, ReportOpenView, ReportSubmitView, ReportUpdateView)

urlpatterns = [
    path("installations/", ReportListView.as_view(), name="installation-list"),
    path("installations/open/", ReportOpenView.as_view(), name="installation-open"),
    path("installations/<int:pk>/", ReportDetailView.as_view(), name="installation-detail"),
    path("installations/<int:pk>/update/", ReportUpdateView.as_view(), name="installation-update"),
    path("installations/<int:pk>/units/", InstalledUnitView.as_view(), name="installation-units"),
    path("installations/<int:pk>/photos/", PhotoView.as_view(), name="installation-photos"),
    path("installations/<int:pk>/submit/", ReportSubmitView.as_view(), name="installation-submit"),
    path("installations/<int:pk>/decide/", ReportDecideView.as_view(), name="installation-decide"),
]
