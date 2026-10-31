"""URL routes for F01 and F02."""

from django.urls import path

from .views import (
    ContactLogListCreateView,
    EnquiryAssignView,
    EnquiryBillView,
    EnquiryCreateView,
    EnquiryListView,
    EnquiryStatusView,
    DuplicateReviewView,
    EnquiryActivityView,
    SiteListView,
)

urlpatterns = [
    # F10 needs somewhere to send a crew.
    path("sites/", SiteListView.as_view(), name="site-list"),
    path("enquiries/<int:pk>/duplicate-review/", DuplicateReviewView.as_view(), name="enquiry-duplicate-review"),
    path("enquiries/<int:pk>/activity/", EnquiryActivityView.as_view(), name="enquiry-activity"),
    # F01
    path("enquiries/", EnquiryListView.as_view(), name="enquiry-list"),
    path("enquiries/submit/", EnquiryCreateView.as_view(), name="enquiry-create"),
    path("enquiries/<int:pk>/bill/", EnquiryBillView.as_view(), name="enquiry-bill"),

    # F02
    path("enquiries/<int:pk>/assign/", EnquiryAssignView.as_view(), name="enquiry-assign"),
    path("enquiries/<int:pk>/status/", EnquiryStatusView.as_view(), name="enquiry-status"),
    path("enquiries/<int:pk>/contacts/", ContactLogListCreateView.as_view(), name="enquiry-contacts"),
]
