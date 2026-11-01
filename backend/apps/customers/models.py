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

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from apps.core.api import business_date
from apps.core.models import record_event

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
    How far an enquiry has travelled through sales.

    Lost is reachable from any open state and always carries a reason.
    """

    NEW = "new", "New"
    CONTACTING = "contacting", "Contacting"
    QUALIFIED = "qualified", "Qualified"
    SURVEY_SCHEDULED = "survey_scheduled", "Survey scheduled"
    LOST = "lost", "Lost"


# Which statuses may follow which. A transition not listed here is
# rejected, so an enquiry cannot skip from New straight to Survey
# Scheduled without anyone having spoken to the customer.
ALLOWED_STATUS_CHANGES = {
    EnquiryStatus.NEW: [EnquiryStatus.CONTACTING, EnquiryStatus.LOST],
    EnquiryStatus.CONTACTING: [EnquiryStatus.QUALIFIED, EnquiryStatus.LOST],
    EnquiryStatus.QUALIFIED: [EnquiryStatus.SURVEY_SCHEDULED, EnquiryStatus.LOST],
    EnquiryStatus.SURVEY_SCHEDULED: [EnquiryStatus.LOST],
    EnquiryStatus.LOST: [],
}

OPEN_STATUSES = [
    EnquiryStatus.NEW,
    EnquiryStatus.CONTACTING,
    EnquiryStatus.QUALIFIED,
    EnquiryStatus.SURVEY_SCHEDULED,
]


class ContactChannel(models.TextChoices):
    PHONE = "phone", "Phone call"
    WHATSAPP = "whatsapp", "WhatsApp"
    EMAIL = "email", "Email"
    SITE_VISIT = "site_visit", "Site visit"
    OTHER = "other", "Other"


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
    pincode = models.CharField(max_length=6)
    address_key = models.CharField(max_length=450, db_index=True, editable=False, default="")

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

    def save(self, *args, **kwargs):
        self.address_key = normalized_address(self.address_line, self.city, self.state, self.pincode)
        super().save(*args, **kwargs)


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
    revision = models.PositiveIntegerField(default=1)
    qualification_checks = models.JSONField(default=dict, blank=True)
    qualification_reason = models.TextField(blank=True)
    duplicate_review = models.CharField(max_length=20, blank=True)
    duplicate_review_reason = models.TextField(blank=True)
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

    # --- follow-up (F02) ---
    # A lead must never sit unowned with nothing planned. Both are
    # nullable only because a web submission arrives before anyone has
    # picked it up; the manager queue exists to surface exactly that.
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="owned_enquiries",
    )
    next_action = models.CharField(max_length=200, blank=True)
    next_action_due = models.DateField(null=True, blank=True)

    # Why the lead was lost. Required when status becomes Lost.
    lost_reason = models.TextField(blank=True)
    closed_at = models.DateTimeField(null=True, blank=True)

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
            self.reference = f"ENQ-{business_date().year}-{self.id:05d}"
            super().save(update_fields=["reference"])

    # --- follow-up state (F02) ----------------------------------------

    @property
    def is_open(self):
        return self.status in OPEN_STATUSES

    @property
    def is_overdue(self):
        """True when the planned next action has passed its due date."""
        if not self.next_action_due or not self.is_open:
            return False
        return self.next_action_due < business_date()

    @transaction.atomic
    def change_status(self, new_status, *, reason="", next_action="",
                      next_action_due=None, actor=None, qualification_checks=None):
        """
        Moves the enquiry to a new status, refusing invalid jumps.

        Lost always needs a reason: a lead that disappears without one
        teaches the business nothing. Any other open status needs a
        planned next action, so nothing is left with no one due to do
        anything.
        """
        stored = type(self).objects.select_for_update().get(pk=self.pk)
        if stored.revision != self.revision:
            raise ValidationError("This enquiry changed. Refresh before moving it on.")
        allowed = ALLOWED_STATUS_CHANGES.get(self.status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot move an enquiry from {self.get_status_display()} "
                f"to {EnquiryStatus(new_status).label}."
            )

        if new_status == EnquiryStatus.LOST:
            if not reason.strip():
                raise ValidationError("A lost enquiry needs a reason.")
            self.lost_reason = reason.strip()
            self.closed_at = timezone.now()
            self.next_action = ""
            self.next_action_due = None
        else:
            if not next_action.strip():
                raise ValidationError(
                    "Set what happens next before moving this enquiry on."
                )
            if next_action_due is None:
                raise ValidationError({"next_action_due": "Set the next action's due date."})
            if self.owner_id is None:
                raise ValidationError({"owner": "Assign an owner before moving this enquiry on."})
            if new_status == EnquiryStatus.QUALIFIED:
                checks = qualification_checks or {}
                missing = [name for name in QUALIFICATION_CHECKS if checks.get(name) is not True]
                if missing:
                    raise ValidationError({"qualification_checks": "Confirm: " + ", ".join(missing)})
                if not reason.strip():
                    raise ValidationError({"reason": "Record why this lead qualifies."})
                self.qualification_checks = checks
                self.qualification_reason = reason.strip()
            self.next_action = next_action.strip()
            self.next_action_due = next_action_due

        previous_status = self.status
        self.status = new_status
        self.revision += 1
        self.save()
        record_event(self, "status_changed", actor, before={"status": previous_status},
                     after={"status": new_status}, reason=reason)


# ============================================================
# Contact log
# ============================================================

class ContactLog(models.Model):
    """
    One recorded attempt to reach the customer about an enquiry.

    Append-only. A call that went unanswered is as much a part of the
    history as one that did not, so entries are never edited away.
    """

    enquiry = models.ForeignKey(
        Enquiry, on_delete=models.PROTECT, related_name="contact_logs"
    )
    staff = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        related_name="contact_logs",
    )
    channel = models.CharField(max_length=20, choices=ContactChannel.choices)

    # When the contact happened, which may differ from when it was
    # typed in. Both are kept, per the time rule in spec.md section 6.
    contacted_at = models.DateTimeField()
    summary = models.TextField()
    reached_customer = models.BooleanField(
        default=True, help_text="False for a missed call or no reply."
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-contacted_at", "-id"]

    def __str__(self):
        return f"{self.enquiry.reference} - {self.get_channel_display()}"


# ============================================================
# Review inputs
# ============================================================

QUALIFICATION_CHECKS = ("roof", "consumption", "grid", "requirements", "documents")


def normalized_address(address_line, city, state, pincode):
    """Ignore punctuation and spacing, while retaining locality and postcode."""
    parts = (address_line, city, state, pincode)
    return "|".join("".join(character for character in part.casefold() if character.isalnum())
                    for part in parts)
