"""URL routes for F03."""

from django.urls import path

from .views import (
    RevisionCreateView,
    RevisionReviewView,
    RevisionSubmitView,
    SurveyDetailView,
    SurveyListView,
    SurveyStartView,
)

urlpatterns = [
    path("surveys/", SurveyListView.as_view(), name="survey-list"),
    path("surveys/start/", SurveyStartView.as_view(), name="survey-start"),
    path("surveys/<int:pk>/", SurveyDetailView.as_view(), name="survey-detail"),
    path("surveys/<int:pk>/revisions/", RevisionCreateView.as_view(), name="revision-create"),
    path("revisions/<int:pk>/submit/", RevisionSubmitView.as_view(), name="revision-submit"),
    path("revisions/<int:pk>/review/", RevisionReviewView.as_view(), name="revision-review"),
]
