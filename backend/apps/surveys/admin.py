"""Admin screens for surveys."""

from django.contrib import admin
from apps.core.admin import ReadOnlyRecordAdmin

from .models import Survey, SurveyPhoto, SurveyRevision


@admin.register(Survey)
class SurveyAdmin(ReadOnlyRecordAdmin):
    list_display = ("enquiry", "is_approved", "created_at")


@admin.register(SurveyRevision)
class SurveyRevisionAdmin(ReadOnlyRecordAdmin):
    list_display = (
        "survey", "revision_number", "status",
        "recommended_capacity_kw", "surveyed_by", "surveyed_at",
    )
    list_filter = ("status", "recommended_system_type", "roof_type")


admin.site.register(SurveyPhoto, ReadOnlyRecordAdmin)
