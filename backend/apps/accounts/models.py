"""
Staff accounts and roles.

The application has one user type: a staff member. Customers are never
users — they submit the public enquiry form, sign on a staff-held
device, and (later) use Telegram. See spec.md section 5.

A staff member may hold several roles at once, so roles are a
many-to-many relation rather than a single field. Permission checks read
these roles; the matrix lives in rules.md section 4.
"""

from django.contrib.auth.models import AbstractUser
from django.db import models


# ============================================================
# Roles
# ============================================================

class Role(models.TextChoices):
    """The eight staff roles from spec.md section 5."""

    ADMINISTRATOR = "administrator", "Administrator"
    SALES = "sales", "Sales"
    OPERATIONS_MANAGER = "operations_manager", "Operations Manager"
    WAREHOUSE = "warehouse", "Warehouse"
    TECHNICIAN = "technician", "Technician"
    SUPPORT = "support", "Support"
    FINANCE = "finance", "Finance"
    DIRECTOR = "director", "Director"


# ============================================================
# User
# ============================================================

class User(AbstractUser):
    """
    A staff member.

    Swapped in via AUTH_USER_MODEL before the first migration, because
    Django cannot change the user model cleanly afterwards.
    """

    phone = models.CharField(max_length=20, blank=True)
    roles = models.JSONField(
        default=list,
        blank=True,
        help_text="List of Role values. A staff member may hold several.",
    )
    is_active_staff = models.BooleanField(
        default=True,
        help_text="Cleared when someone leaves, instead of deleting the record.",
    )

    class Meta:
        db_table = "accounts_user"

    def __str__(self):
        return self.get_full_name() or self.username

    # --- role helpers -------------------------------------------------

    def has_role(self, role):
        """True when this user holds the given role, or is an administrator."""
        return (
            Role.ADMINISTRATOR in self.roles
            or role in self.roles
        )

    def has_any_role(self, *roles):
        """True when this user holds at least one of the given roles."""
        return any(self.has_role(role) for role in roles)
