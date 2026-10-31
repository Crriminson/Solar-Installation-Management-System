"""
F09 - reservation, packing, scanning and dispatch.

One fulfilment per order, carrying it from "nothing picked yet" to
"delivered and signed for":

    Fulfilment   - the order's journey out of the warehouse.
    PackingLine  - one product the order needs, and how much is packed.
    ScanEvent    - one physical item confirmed into the box.

Reservation is where the real contention is. Two orders must never hold
the same serialized unit, so reserving locks each candidate row and
checks its status inside the transaction rather than trusting a count
read a moment earlier.

Delivery is what activates warranties (F12). Not packing, not dispatch -
the clock starts when the customer has the equipment.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


ZERO = Decimal("0.00")


# ============================================================
# Choices
# ============================================================

class FulfilmentStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    RESERVED = "reserved", "Reserved"
    PACKED = "packed", "Packed"
    DISPATCHED = "dispatched", "Dispatched"
    DELIVERED = "delivered", "Delivered"
    BLOCKED = "blocked", "Blocked - short of stock"


# Which states may follow which. Blocked is reachable from Pending only:
# once stock is held, a shortage is somebody else's order's problem.
ALLOWED_FULFILMENT_MOVES = {
    FulfilmentStatus.PENDING: [FulfilmentStatus.RESERVED, FulfilmentStatus.BLOCKED],
    FulfilmentStatus.BLOCKED: [FulfilmentStatus.RESERVED],
    FulfilmentStatus.RESERVED: [FulfilmentStatus.PACKED, FulfilmentStatus.PENDING],
    FulfilmentStatus.PACKED: [FulfilmentStatus.DISPATCHED],
    FulfilmentStatus.DISPATCHED: [FulfilmentStatus.DELIVERED],
    FulfilmentStatus.DELIVERED: [],
}


# ============================================================
# Fulfilment
# ============================================================

class Fulfilment(models.Model):
    """
    One order's passage out of the warehouse.

    Initial deliveries are complete-order deliveries (D018). A shortage
    blocks the whole fulfilment and raises a procurement action rather
    than sending half a system to a roof.
    """

    order = models.OneToOneField(
        "orders.Order", on_delete=models.PROTECT, related_name="fulfilment"
    )
    status = models.CharField(
        max_length=20, choices=FulfilmentStatus.choices, default=FulfilmentStatus.PENDING
    )
    blocked_reason = models.TextField(
        blank=True, help_text="What is short, so procurement can act on it."
    )

    # --- dispatch ---
    dispatched_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="dispatches",
    )
    dispatched_at = models.DateTimeField(null=True, blank=True)
    carrier_reference = models.CharField(
        max_length=100, blank=True, help_text="Vehicle number or courier consignment."
    )

    # --- delivery ---
    # The time the goods reached the customer, against the time it was
    # keyed in. Both are kept, per spec.md section 6.
    delivered_at = models.DateTimeField(null=True, blank=True)
    delivery_recorded_at = models.DateTimeField(null=True, blank=True)
    delivered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT,
        null=True, blank=True, related_name="deliveries",
    )
    received_by_name = models.CharField(max_length=150, blank=True)
    delivery_proof = models.ImageField(upload_to="delivery_proof/", blank=True)
    delivery_notes = models.TextField(blank=True)

    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            # Delivery is what starts the warranty clock, so it cannot be
            # recorded without saying who took the goods.
            models.CheckConstraint(
                condition=~models.Q(status="delivered") | ~models.Q(received_by_name=""),
                name="delivery_names_its_recipient",
            ),
        ]

    def __str__(self):
        return f"Fulfilment of {self.order.reference}"

    def delete(self, *args, **kwargs):
        raise ValidationError("A fulfilment record is never deleted.")

    @property
    def is_complete(self):
        """Every line has as much packed as the order needs."""
        return all(line.is_complete for line in self.lines.all())

    def shortages(self):
        """Lines the warehouse cannot satisfy, for the blocked message."""
        return [line for line in self.lines.all() if not line.is_complete]


# ============================================================
# Packing lines
# ============================================================

class PackingLine(models.Model):
    """
    One product the order needs, copied from the accepted quotation.

    packed_quantity is maintained here so the database can refuse to let
    more be packed than the order calls for.
    """

    fulfilment = models.ForeignKey(
        Fulfilment, on_delete=models.PROTECT, related_name="lines"
    )
    product = models.ForeignKey("catalogue.Product", on_delete=models.PROTECT)
    sku = models.CharField(max_length=40)
    description = models.CharField(max_length=250)
    unit = models.CharField(max_length=20)
    tracking_method = models.CharField(max_length=20)

    required_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    reserved_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)
    packed_quantity = models.DecimalField(max_digits=12, decimal_places=2, default=ZERO)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["fulfilment", "product"],
                name="one_packing_line_per_product",
            ),
            # Packing more than the order calls for is a picking error.
            models.CheckConstraint(
                condition=models.Q(packed_quantity__lte=models.F("required_quantity")),
                name="not_packed_beyond_required",
            ),
            models.CheckConstraint(
                condition=models.Q(reserved_quantity__lte=models.F("required_quantity")),
                name="not_reserved_beyond_required",
            ),
        ]

    def __str__(self):
        return f"{self.required_quantity} {self.unit} of {self.sku}"

    @property
    def is_complete(self):
        return self.packed_quantity >= self.required_quantity

    @property
    def outstanding_quantity(self):
        return self.required_quantity - self.packed_quantity


# ============================================================
# Scans
# ============================================================

class ScanEvent(models.Model):
    """
    One physical item confirmed into the box.

    Exactly one of unit or lot is named. A serialized unit is scanned
    once and counts as one; a lot is scanned with a counted quantity,
    because a drum of cable has no per-metre identity.

    A manual entry is allowed when a label will not read, but it is
    permission-controlled and carries a reason, so the audit trail shows
    which items were confirmed by eye rather than by scanner.
    """

    line = models.ForeignKey(PackingLine, on_delete=models.PROTECT, related_name="scans")
    unit = models.ForeignKey(
        "inventory.SerializedUnit", on_delete=models.PROTECT,
        null=True, blank=True, related_name="pack_scans",
    )
    lot = models.ForeignKey(
        "inventory.BatchLot", on_delete=models.PROTECT,
        null=True, blank=True, related_name="pack_scans",
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )

    entered_manually = models.BooleanField(default=False)
    manual_reason = models.TextField(blank=True)

    scanned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="pack_scans"
    )
    scanned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(unit__isnull=False, lot__isnull=True)
                           | models.Q(unit__isnull=True, lot__isnull=False)),
                name="scan_names_one_stock_item",
            ),
            # The same unit cannot be scanned into the same box twice.
            models.UniqueConstraint(
                fields=["line", "unit"],
                condition=models.Q(unit__isnull=False),
                name="one_scan_per_unit_per_line",
            ),
            models.CheckConstraint(
                condition=~models.Q(entered_manually=True) | ~models.Q(manual_reason=""),
                name="manual_entry_carries_a_reason",
            ),
        ]

    def __str__(self):
        subject = self.unit.asset_id if self.unit else self.lot.batch_id
        return f"{subject} x {self.quantity}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("A scan is a record of an event; it is not edited.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Scans are not deleted. Unpack the order instead.")
