"""Admin screens for the settings that have no screen of their own."""

from django.contrib import admin

from .models import SizingDefaults, WarrantyPolicy


@admin.register(WarrantyPolicy)
class WarrantyPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "duration_months")


@admin.register(SizingDefaults)
class SizingDefaultsAdmin(admin.ModelAdmin):
    list_display = ("cable_waste_factor", "cable_termination_buffer_m")
