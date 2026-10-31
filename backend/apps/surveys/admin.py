"""Admin screens for surveys."""

from django.contrib import admin

from .models import Survey, SurveyPhoto, SurveyRevision


@admin.register(Survey)
class SurveyAdmin(admin.ModelAdmin):
    list_display = ("enquiry", "is_approved", "created_at")


@admin.register(SurveyRevision)
class SurveyRevisionAdmin(admin.ModelAdmin):
    list_display = (
        "survey", "revision_number", "status",
        "recommended_capacity_kw", "surveyed_by", "surveyed_at",
    )
    list_filter = ("status", "recommended_system_type", "roof_type")


admin.site.register(SurveyPhoto)
