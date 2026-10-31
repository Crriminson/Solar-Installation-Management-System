"""Support routes under the versioned API."""

from django.urls import path

from .views import (CustomerEquipmentView, LookupView, TicketActionView, TicketDetailView,
                    TicketListView, TicketPhotoView, TicketRaiseView, TicketReviewView,
                    TicketVisitView)

urlpatterns = [
    path("support/lookup/", LookupView.as_view(), name="support-lookup"),
    path("support/customers/<int:pk>/", CustomerEquipmentView.as_view(), name="support-customer"),
    path("tickets/", TicketListView.as_view(), name="ticket-list"),
    path("tickets/raise/", TicketRaiseView.as_view(), name="ticket-raise"),
    path("tickets/<int:pk>/", TicketDetailView.as_view(), name="ticket-detail"),
    path("tickets/<int:pk>/photos/", TicketPhotoView.as_view(), name="ticket-photos"),
    path("tickets/<int:pk>/review/", TicketReviewView.as_view(), name="ticket-review"),
    path("tickets/<int:pk>/visit/", TicketVisitView.as_view(), name="ticket-visit"),
    path("tickets/<int:pk>/<str:action>/", TicketActionView.as_view(), name="ticket-action"),
]
