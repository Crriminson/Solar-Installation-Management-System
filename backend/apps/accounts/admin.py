"""Admin registration for the staff user model."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class StaffUserAdmin(UserAdmin):
    list_display = ("username", "email", "first_name", "last_name", "is_active_staff")
    fieldsets = UserAdmin.fieldsets + (
        ("Solar platform", {"fields": ("phone", "roles", "is_active_staff")}),
    )
