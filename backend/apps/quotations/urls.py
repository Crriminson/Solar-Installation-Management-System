"""Explicit quotation actions under the versioned API."""

from django.urls import path
from .views import (QuoteAcceptView, QuoteActionView, QuoteActivityView, QuoteDetailView,
                    QuoteGenerateView, QuoteListView, QuotePresentView)

urlpatterns = [
    path("quotations/", QuoteListView.as_view(), name="quotation-list"),
    path("quotations/generate/", QuoteGenerateView.as_view(), name="quotation-generate"),
    path("quotations/<int:pk>/", QuoteDetailView.as_view(), name="quotation-detail"),
    path("quotations/<int:pk>/activity/", QuoteActivityView.as_view(), name="quotation-activity"),
    path("quotations/<int:pk>/present/", QuotePresentView.as_view(), name="quotation-present"),
    path("quotations/<int:pk>/accept/", QuoteAcceptView.as_view(), name="quotation-accept"),
    # Keep last: this pattern would otherwise swallow the named actions above.
    path("quotations/<int:pk>/<str:action>/", QuoteActionView.as_view(), name="quotation-action"),
]
