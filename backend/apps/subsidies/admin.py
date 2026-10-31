"""Administrators maintain new rule versions; active history stays read-only."""

from django.contrib import admin
from .models import SchemeVersion


@admin.register(SchemeVersion)
class SchemeVersionAdmin(admin.ModelAdmin):
    list_display = ["scheme", "version", "jurisdiction", "rule_type", "is_active", "last_checked"]

    def has_change_permission(self, request, obj=None):
        return request.user.has_role("administrator") and not (obj and obj.is_active)

    def has_add_permission(self, request):
        return request.user.has_role("administrator")

    def has_delete_permission(self, request, obj=None):
        return False
