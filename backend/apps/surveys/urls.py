"""URL routes for F03."""

from django.urls import path

from .views import (
    RevisionCreateView,
    RevisionPhotoView,
    RevisionReviewView,
    RevisionSubmitView,
    SurveyDetailView,
    SurveyListView,
    SurveyPhotoFileView,
    SurveyStartView,
    SurveyAssignView,
    RevisionEditView,
    RevisionActivityView,
)

urlpatterns = [
    path("revisions/<int:pk>/activity/", RevisionActivityView.as_view(), name="revision-activity"),
    path("surveys/<int:pk>/assign/", SurveyAssignView.as_view(), name="survey-assign"),
    path("revisions/<int:pk>/", RevisionEditView.as_view(), name="revision-edit"),
    path("surveys/", SurveyListView.as_view(), name="survey-list"),
    path("surveys/start/", SurveyStartView.as_view(), name="survey-start"),
    path("surveys/<int:pk>/", SurveyDetailView.as_view(), name="survey-detail"),
    path("surveys/<int:pk>/revisions/", RevisionCreateView.as_view(), name="revision-create"),
    path("revisions/<int:pk>/submit/", RevisionSubmitView.as_view(), name="revision-submit"),
    path("revisions/<int:pk>/review/", RevisionReviewView.as_view(), name="revision-review"),
    path("revisions/<int:pk>/photos/", RevisionPhotoView.as_view(), name="revision-photos"),
    path("survey-photos/<int:pk>/", SurveyPhotoFileView.as_view(), name="survey-photo-file"),
]
