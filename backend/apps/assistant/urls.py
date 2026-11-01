"""Staff assistant routes under the versioned API."""

from django.urls import path

from .views import AskView, StatusView

urlpatterns = [
    path("assistant/status/", StatusView.as_view(), name="assistant-status"),
    path("assistant/ask/", AskView.as_view(), name="assistant-ask"),
]
