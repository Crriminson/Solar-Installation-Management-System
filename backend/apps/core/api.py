"""Consistent staff access, bounded lists and stale-edit responses."""

from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import BasePermission, SAFE_METHODS

from apps.accounts.models import Role


class Conflict(APIException):
    status_code = 409
    default_detail = "This record changed. Refresh and review the change; your input has not been saved."


def check_revision(record, data):
    """The caller must lock the row before comparing its revision."""
    value = data.get("revision")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError({"revision": ["Send the record revision shown on screen."]})
    if value != record.revision:
        raise Conflict()


def exact_decimals(data):
    """
    Turns every Decimal in a plain response into text.

    Serializers already do this, but DRF renders a bare Decimal as a float,
    and money is never binary floating point (spec.md section 6).
    """
    if isinstance(data, Decimal):
        return str(data)
    if isinstance(data, dict):
        return {key: exact_decimals(value) for key, value in data.items()}
    if isinstance(data, list):
        return [exact_decimals(value) for value in data]
    return data


def business_date(moment=None):
    """The Asia/Kolkata calendar date of a moment, or of right now."""
    return timezone.localdate(moment, timezone=ZoneInfo(settings.BUSINESS_TIMEZONE))


class StaffAccess(BasePermission):
    """Feature views declare the roles they allow; inactive staff never enter."""

    message = "Your role cannot perform this action. Ask an administrator for access."

    def has_permission(self, request, view):
        user = request.user
        if not user.is_authenticated or not user.is_active or not user.is_active_staff:
            return False
        roles = view.read_roles if request.method in SAFE_METHODS else view.write_roles
        return user.has_any_role(*roles)


class ActiveStaff(BasePermission):
    message = "An active staff account is required. Ask an administrator for access."

    def has_permission(self, request, view):
        user = request.user
        return user.is_authenticated and user.is_active and user.is_active_staff


class SalesAccess(StaffAccess):
    def has_permission(self, request, view):
        view.read_roles = (Role.SALES, Role.OPERATIONS_MANAGER, Role.DIRECTOR)
        view.write_roles = (Role.SALES, Role.OPERATIONS_MANAGER)
        return super().has_permission(request, view)


class BoundedPagination(PageNumberPagination):
    page_size = settings.DEFAULT_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = settings.MAX_PAGE_SIZE
