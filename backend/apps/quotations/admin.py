"""Administrators edit defaults; quotation documents are viewed through the application."""

from django.contrib import admin
from .models import QuotationSettings


@admin.register(QuotationSettings)
class QuotationSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return not QuotationSettings.objects.exists() and request.user.has_role("administrator")

    def has_change_permission(self, request, obj=None):
        return request.user.has_role("administrator")

    def has_delete_permission(self, request, obj=None):
        return False
