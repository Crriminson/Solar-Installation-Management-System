"""URL routes for F01 and F02."""

from django.urls import path

from .views import (
    ContactLogListCreateView,
    EnquiryAssignView,
    EnquiryCreateView,
    EnquiryListView,
    EnquiryStatusView,
)

urlpatterns = [
    # F01
    path("enquiries/", EnquiryListView.as_view(), name="enquiry-list"),
    path("enquiries/submit/", EnquiryCreateView.as_view(), name="enquiry-create"),

    # F02
    path("enquiries/<int:pk>/assign/", EnquiryAssignView.as_view(), name="enquiry-assign"),
    path("enquiries/<int:pk>/status/", EnquiryStatusView.as_view(), name="enquiry-status"),
    path("enquiries/<int:pk>/contacts/", ContactLogListCreateView.as_view(), name="enquiry-contacts"),
]
