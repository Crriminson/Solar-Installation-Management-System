"""Admin screens for the settings that have no screen of their own."""

from django.contrib import admin

from apps.core.models import record_event

from .models import WARRANTY_TERM_FIELDS, SizingDefaults, WarrantyPolicy


def _policy_terms(policy):
    return {name: getattr(policy, name) for name in ("version", *WARRANTY_TERM_FIELDS)}


@admin.register(WarrantyPolicy)
class WarrantyPolicyAdmin(admin.ModelAdmin):
    list_display = ("name", "version", "duration_months", "fresh_period_on_replacement")
    readonly_fields = ("version",)

    def save_model(self, request, obj, form, change):
        """The row only holds the latest terms, so the audit trail keeps the rest."""
        before = _policy_terms(WarrantyPolicy.objects.get(pk=obj.pk)) if change else {}
        super().save_model(request, obj, form, change)

        if not change:
            record_event(obj, "created", request.user, after=_policy_terms(obj))
        elif before["version"] != obj.version:
            record_event(obj, "revised", request.user, before=before,
                         after=_policy_terms(obj))


@admin.register(SizingDefaults)
class SizingDefaultsAdmin(admin.ModelAdmin):
    list_display = ("cable_waste_factor", "cable_termination_buffer_m")
