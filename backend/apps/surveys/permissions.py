"""Survey access follows role and technician assignment, including private photos."""

from django.db.models import Q
from rest_framework.exceptions import PermissionDenied

from apps.accounts.models import Role
from apps.core.api import StaffAccess


class SurveyAccess(StaffAccess):
    def has_permission(self, request, view):
        view.read_roles = (Role.SALES, Role.OPERATIONS_MANAGER, Role.TECHNICIAN, Role.DIRECTOR)
        view.write_roles = (Role.SALES, Role.OPERATIONS_MANAGER, Role.TECHNICIAN)
        return super().has_permission(request, view)


def scoped_surveys(queryset, user):
    if user.has_any_role(Role.SALES, Role.OPERATIONS_MANAGER, Role.DIRECTOR):
        return queryset
    return queryset.filter(assigned_to=user)


def require_capture(survey, user):
    if user.has_role(Role.ADMINISTRATOR):
        return
    if not user.has_role(Role.TECHNICIAN) or survey.assigned_to_id != user.pk:
        raise PermissionDenied("Only the assigned technician may record this survey.")
