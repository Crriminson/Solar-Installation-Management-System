"""F19 routes."""

from django.urls import path

from .views import DocumentDownload, DocumentGenerate, DocumentList

urlpatterns = [
    path("documents/", DocumentList.as_view(), name="documents"),
    path("documents/<int:pk>/download/", DocumentDownload.as_view(), name="document-download"),
    path("documents/<str:kind>/<int:pk>/generate/", DocumentGenerate.as_view(), name="document-generate"),
]
