"""Admin screens for customers, sites and enquiries."""

from django.contrib import admin

from .models import Customer, Enquiry, Site


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("full_name", "phone", "customer_type", "created_at")
    search_fields = ("full_name", "phone", "email")


@admin.register(Site)
class SiteAdmin(admin.ModelAdmin):
    list_display = ("address_line", "city", "state", "customer")
    search_fields = ("address_line", "city", "pincode")


@admin.register(Enquiry)
class EnquiryAdmin(admin.ModelAdmin):
    list_display = ("reference", "site", "source", "status", "created_at")
    list_filter = ("status", "source", "requested_system_type")
    search_fields = ("reference", "site__customer__full_name")
    readonly_fields = ("reference", "created_at", "updated_at")
