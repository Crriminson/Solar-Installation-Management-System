"""
Who may do what in the catalogue. See rules.md section 4.

Anyone signed in can read the catalogue. Maintaining it belongs to the
operations manager. Taking a package live is a separate, higher step,
because that is what lets it reach a customer (D028).
"""

from rest_framework.permissions import SAFE_METHODS, BasePermission

from apps.accounts.models import Role


def can_manage_catalogue(user):
    return user.has_any_role(Role.OPERATIONS_MANAGER)


def can_review_packages(user):
    """Spec.md section 14: templates are owner-reviewed before activation."""
    return user.has_role(Role.ADMINISTRATOR)


def can_view_costs(user):
    """
    Purchase cost is restricted regardless of role, unless granted.

    Finance allocates it, the director reads it, and the operations
    manager maintains it. Sales must never see it.
    """
    return user.has_any_role(Role.FINANCE, Role.DIRECTOR, Role.OPERATIONS_MANAGER)


class CatalogueWriteAccess(BasePermission):
    """Reads for any staff member, writes for those who maintain it."""

    message = "Only an operations manager may change the catalogue."

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        return request.method in SAFE_METHODS or can_manage_catalogue(request.user)
