"""
F01 — customers, sites and enquiries.

Three records, in a chain:

    Customer  — the person or business. One customer, many sites.
    Site      — a roof at an address. One site, many projects later on.
    Enquiry   — a request for a system at a site. Never deleted.

The rule that shapes this file: an enquiry must never vanish. It is
saved before the sender is told it succeeded, it gets a reference
number, and a suspected duplicate is flagged for a human rather than
merged or dropped automatically.
"""

from django.db import models, transaction

from .constants import STATE_CHOICES


# ============================================================
# Choices
# ============================================================

class CustomerType(models.TextChoices):
    RESIDENTIAL = "residential", "Residential"
    COMMERCIAL = "commercial", "Commercial"


class SystemType(models.TextChoices):
    ON_GRID = "on_grid", "On-Grid"
    OFF_GRID = "off_grid", "Off-Grid"
    UNDECIDED = "undecided", "Not decided yet"


class EnquirySource(models.TextChoices):
    """Where the enquiry came from. Always recorded, never guessed."""

    WEB_FORM = "web_form", "Website form"
    PHONE = "phone", "Phone call"
    WHATSAPP = "whatsapp", "WhatsApp message"
    WALK_IN = "walk_in", "Walk-in"
    REFERRAL = "referral", "Referral"
    OTHER = "other", "Other"


class EnquiryStatus(models.TextChoices):
    """
    Only the entry state belongs to F01. Qualification and follow-up
    states are added by F02.
    """

    NEW = "new", "New"


# ============================================================
# Customer
# ============================================================

class Customer(models.Model):
    """A person or business that may own several sites."""

    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True)
    customer_type = models.CharField(
        max_length=20,
        choices=CustomerType.choices,
        default=CustomerType.RESIDENTIAL,
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["full_name", "id"]

    def __str__(self):
        return f"{self.full_name} ({self.phone})"


# ============================================================
# Site
# ============================================================

class Site(models.Model):
    """A roof at an address. Belongs to one customer."""

    customer = models.ForeignKey(
        Customer, on_delete=models.PROTECT, related_name="sites"
    )

    address_line = models.CharField(max_length=255)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=60, choices=STATE_CHOICES)
    pincode = models.CharField(max_length=10)

    # Area with no shade for most of the day. Drives how many panels fit.
    shadow_free_roof_area_sqm = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return f"{self.address_line}, {self.city}"


# ============================================================
# Enquiry
# ============================================================

class Enquiry(models.Model):
    """
    A request for a solar system at a site.

    Bill amount and consumption are deliberately separate fields. A bill
    in rupees is not a measure of units used: tariffs are slabbed and
    vary by state, so one can never be calculated from the other.
    """

    reference = models.CharField(max_length=20, unique=True, editable=False)
    site = models.ForeignKey(Site, on_delete=models.PROTECT, related_name="enquiries")
    source = models.CharField(max_length=20, choices=EnquirySource.choices)
    status = models.CharField(
        max_length=20, choices=EnquiryStatus.choices, default=EnquiryStatus.NEW
    )

    # What the customer thinks they want. Confirmed later by the survey.
    requested_system_type = models.CharField(
        max_length=20, choices=SystemType.choices, default=SystemType.UNDECIDED
    )
    requested_capacity_kw = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True
    )

    # Electricity usage. Either may be unknown at enquiry time.
    electricity_connection_number = models.CharField(max_length=50, blank=True)
    monthly_consumption_kwh = models.DecimalField(
        max_digits=8, decimal_places=2, null=True, blank=True
    )
    monthly_bill_amount = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True
    )
    billing_period_start = models.DateField(null=True, blank=True)
    billing_period_end = models.DateField(null=True, blank=True)
    electricity_bill = models.FileField(
        upload_to="electricity_bills/", blank=True
    )

    notes = models.TextField(blank=True)

    # Set when another customer already has this phone number. The
    # enquiry is still saved; a human decides whether they are the same
    # person. Never merge or discard automatically.
    possible_duplicate_of = models.ForeignKey(
        Customer,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="flagged_duplicate_enquiries",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "-id"]
        verbose_name_plural = "enquiries"

    def __str__(self):
        return self.reference

    def save(self, *args, **kwargs):
        """
        Saves the enquiry, assigning a reference on first insert.

        The reference contains the row id, which only exists after the
        insert, so a new enquiry is written twice inside one
        transaction. Both writes succeed or neither does, so an enquiry
        can never exist without a reference.
        """
        if self.reference:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            super().save(*args, **kwargs)
            self.reference = f"ENQ-{self.created_at.year}-{self.id:05d}"
            super().save(update_fields=["reference"])
