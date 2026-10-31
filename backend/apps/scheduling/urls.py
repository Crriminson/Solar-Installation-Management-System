"""Scheduling routes under the versioned API."""

from django.urls import path

from .views import JobActionView, JobCreateView, JobDetailView, JobListView

urlpatterns = [
    path("jobs/", JobListView.as_view(), name="job-list"),
    path("jobs/create/", JobCreateView.as_view(), name="job-create"),
    path("jobs/<int:pk>/", JobDetailView.as_view(), name="job-detail"),
    # Keep last: this pattern would otherwise swallow the named routes above.
    path("jobs/<int:pk>/<str:action>/", JobActionView.as_view(), name="job-action"),
]
