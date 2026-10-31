"""URL routes for F01."""

from django.urls import path

from .views import EnquiryCreateView, EnquiryListView

urlpatterns = [
    path("enquiries/", EnquiryListView.as_view(), name="enquiry-list"),
    path("enquiries/submit/", EnquiryCreateView.as_view(), name="enquiry-create"),
]
