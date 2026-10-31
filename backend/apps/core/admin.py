"""Operational evidence is viewed in admin; business actions run through the authorized API."""

from django.contrib import admin


class ReadOnlyRecordAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
