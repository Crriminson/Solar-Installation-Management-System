"""
F08 - purchasing, receiving and inventory.

Stock has to have an auditable origin, so nothing appears in the
warehouse without a purchase behind it:

    Supplier        - who we buy from.
    PurchaseOrder   - what we asked for, and what the supplier billed.
    GoodsReceipt    - what actually turned up, and when.
    SerializedUnit  - one physical unit with its own identity.
    BatchLot        - a quantity of something that has no unit identity.
    StockMovement   - every change of state, without exception.

The two stock shapes are deliberate. An inverter has a manufacturer
serial, so it is tracked one unit at a time. A hundred metres of cable
does not, and inventing a serial for it would be a lie, so cable is
tracked by the batch it arrived in and a quantity (spec.md F08).

Nothing changes a stock item's state except move_stock() in services.py,
which writes the movement in the same transaction. A status written any
other way is a bug.
"""

from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models, transaction


ZERO = Decimal("0.00")
SMALLEST_QUANTITY = Decimal("0.01")


# ============================================================
# Choices
# ============================================================

class PurchaseStatus(models.TextChoices):
    DRAFT = "draft", "Draft"
    PLACED = "placed", "Placed with supplier"
    PART_RECEIVED = "part_received", "Partly received"
    RECEIVED = "received", "Received"
    CANCELLED = "cancelled", "Cancelled"


class SupplierPaymentStatus(models.TextChoices):
    UNPAID = "unpaid", "Unpaid"
    PART_PAID = "part_paid", "Part paid"
    PAID = "paid", "Paid"


class StockStatus(models.TextChoices):
    """
    Where a unit stands.

    On-hand is not stored: it is Available plus Reserved. Storing it too
    would give two answers to the same question.
    """

    AVAILABLE = "available", "Available"
    RESERVED = "reserved", "Reserved for an order"
    DISPATCHED = "dispatched", "Dispatched"
    DELIVERED = "delivered", "Delivered"
    INSTALLED = "installed", "Installed"
    RETURNED = "returned", "Returned"
    QUARANTINED = "quarantined", "Quarantined"


# Stock still physically ours and countable in the warehouse.
ON_HAND_STATUSES = [StockStatus.AVAILABLE, StockStatus.RESERVED]

# Which states may follow which. Dispatch, delivery and installation are
# F09 to F11; quarantine and return are reachable from anywhere a unit is
# still ours, because damage is found whenever it is found.
ALLOWED_STOCK_MOVES = {
    StockStatus.AVAILABLE: [StockStatus.RESERVED, StockStatus.QUARANTINED,
                            StockStatus.RETURNED],
    StockStatus.RESERVED: [StockStatus.AVAILABLE, StockStatus.DISPATCHED,
                           StockStatus.QUARANTINED],
    StockStatus.DISPATCHED: [StockStatus.DELIVERED, StockStatus.RETURNED],
    StockStatus.DELIVERED: [StockStatus.INSTALLED, StockStatus.RETURNED],
    StockStatus.INSTALLED: [StockStatus.RETURNED],
    StockStatus.RETURNED: [StockStatus.QUARANTINED, StockStatus.AVAILABLE],
    StockStatus.QUARANTINED: [StockStatus.AVAILABLE, StockStatus.RETURNED],
}


# ============================================================
# Supplier and purchasing
# ============================================================

class Supplier(models.Model):
    name = models.CharField(max_length=150, unique=True)
    contact_name = models.CharField(max_length=150, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    gstin = models.CharField(max_length=15, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class PurchaseOrder(models.Model):
    """What we asked a supplier for, and what they billed us."""

    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="orders")
    reference = models.CharField(max_length=30, unique=True, blank=True)
    status = models.CharField(
        max_length=20, choices=PurchaseStatus.choices, default=PurchaseStatus.DRAFT
    )

    supplier_invoice_reference = models.CharField(max_length=100, blank=True)
    supplier_invoice_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(ZERO)],
    )
    supplier_payment_status = models.CharField(
        max_length=20, choices=SupplierPaymentStatus.choices,
        default=SupplierPaymentStatus.UNPAID,
    )

    raised_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchase_orders"
    )
    placed_on = models.DateField(null=True, blank=True)
    expected_on = models.DateField(null=True, blank=True)

    revision = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["supplier", "supplier_invoice_reference"],
                condition=~models.Q(supplier_invoice_reference=""),
                name="one_purchase_per_supplier_invoice",
            ),
        ]

    def __str__(self):
        return self.reference or f"Draft purchase from {self.supplier}"

    def save(self, *args, **kwargs):
        if self.reference:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            super().save(*args, **kwargs)
            self.reference = f"PO-{self.created_at.year}-{self.id:05d}"
            super().save(update_fields=["reference"])

    def delete(self, *args, **kwargs):
        raise ValidationError("Purchase orders are cancelled, never deleted.")


class PurchaseOrderLine(models.Model):
    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="lines"
    )
    product = models.ForeignKey("catalogue.Product", on_delete=models.PROTECT)
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(SMALLEST_QUANTITY)]
    )
    received_quantity = models.DecimalField(
        max_digits=12, decimal_places=2, default=ZERO
    )
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )

    class Meta:
        ordering = ["id"]
        constraints = [
            models.UniqueConstraint(
                fields=["purchase_order", "product"],
                name="one_line_per_product_per_purchase",
            ),
            # Receiving more than was ordered is a counting error, not a
            # windfall. Raise a second purchase order instead.
            models.CheckConstraint(
                condition=models.Q(received_quantity__lte=models.F("quantity")),
                name="not_received_beyond_ordered",
            ),
        ]

    def __str__(self):
        return f"{self.quantity} x {self.product.sku}"

    @property
    def outstanding_quantity(self):
        return self.quantity - self.received_quantity


# ============================================================
# Receiving
# ============================================================

class GoodsReceipt(models.Model):
    """One delivery from a supplier. Stock exists only because of one of these."""

    purchase_order = models.ForeignKey(
        PurchaseOrder, on_delete=models.PROTECT, related_name="receipts"
    )
    reference = models.CharField(max_length=30, unique=True, blank=True)
    delivery_note_reference = models.CharField(max_length=100, blank=True)

    # When the lorry arrived, against when it was keyed in.
    received_on = models.DateField()
    recorded_at = models.DateTimeField(auto_now_add=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="goods_received"
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-id"]

    def __str__(self):
        return self.reference or f"Receipt against {self.purchase_order_id}"

    def save(self, *args, **kwargs):
        if self.reference:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            super().save(*args, **kwargs)
            self.reference = f"GRN-{self.received_on.year}-{self.id:05d}"
            super().save(update_fields=["reference"])

    def delete(self, *args, **kwargs):
        raise ValidationError("A goods receipt is evidence of what arrived; it is never deleted.")


# ============================================================
# Stock
# ============================================================

class StockItem(models.Model):
    """
    What serialized units and batch lots have in common.

    Abstract on purpose: the two shapes share a lifecycle and a cost, but
    not an identity, and flattening them into one table would mean a
    nullable serial column that is meaningless for cable.
    """

    product = models.ForeignKey("catalogue.Product", on_delete=models.PROTECT)
    goods_receipt = models.ForeignKey(GoodsReceipt, on_delete=models.PROTECT)
    status = models.CharField(
        max_length=20, choices=StockStatus.choices, default=StockStatus.AVAILABLE
    )
    location = models.CharField(
        max_length=100, default="main", help_text="One warehouse for now (D017)."
    )

    # Reserved and dispatched against this order. Set by F09.
    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, null=True, blank=True
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True

    @property
    def on_hand(self):
        return self.status in ON_HAND_STATUSES


class SerializedUnit(StockItem):
    """
    One physical unit: a panel, inverter, battery or charge controller.

    asset_id is ours and always exists. serial_number is the
    manufacturer's and is blank when they did not print one - it is never
    invented to fill the column.
    """

    asset_id = models.CharField(max_length=30, unique=True, blank=True)
    serial_number = models.CharField(max_length=100, blank=True)
    acquisition_cost = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )

    # Filled in on delivery, so a unit can be traced to the roof it is on.
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.PROTECT, null=True, blank=True
    )
    site = models.ForeignKey(
        "customers.Site", on_delete=models.PROTECT, null=True, blank=True
    )

    class Meta:
        ordering = ["-id"]
        constraints = [
            # Two units of the same product cannot carry one serial.
            # Blank is exempt, because many blanks are not a clash.
            models.UniqueConstraint(
                fields=["product", "serial_number"],
                condition=~models.Q(serial_number=""),
                name="one_unit_per_product_serial",
            ),
        ]

    def __str__(self):
        return f"{self.asset_id} ({self.product.sku})"

    def save(self, *args, **kwargs):
        if self.asset_id:
            return super().save(*args, **kwargs)

        with transaction.atomic():
            super().save(*args, **kwargs)
            self.asset_id = f"AST-{self.id:07d}"
            super().save(update_fields=["asset_id"])

    def delete(self, *args, **kwargs):
        raise ValidationError("A unit is quarantined or returned, never deleted.")


class BatchLot(StockItem):
    """
    A quantity of something with no unit identity: cable, connectors.

    The batch id is whatever is printed on the drum or carton. Quantity
    falls as the lot is consumed, and every fall is a movement.
    """

    batch_id = models.CharField(max_length=100)

    # A drum that is partly reserved or dispatched splits into portions.
    # The portion points back at the drum it came off, so the batch is
    # still traceable to one receipt however many pieces it ends up in.
    parent_lot = models.ForeignKey(
        "self", on_delete=models.PROTECT, null=True, blank=True, related_name="portions"
    )
    quantity = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )
    unit = models.CharField(max_length=20)
    unit_cost = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(ZERO)]
    )

    class Meta:
        ordering = ["-id"]
        constraints = [
            # One row per batch as it arrived, so the same drum cannot be
            # booked in twice. Portions split off it are exempt: they are
            # the same physical batch, not another delivery of it.
            models.UniqueConstraint(
                fields=["product", "batch_id", "goods_receipt"],
                condition=models.Q(parent_lot__isnull=True),
                name="one_root_lot_per_product_batch_and_receipt",
            ),
            models.CheckConstraint(
                condition=models.Q(quantity__gte=ZERO),
                name="lot_quantity_not_negative",
            ),
        ]

    def __str__(self):
        return f"{self.batch_id} ({self.quantity} {self.unit} of {self.product.sku})"

    def delete(self, *args, **kwargs):
        raise ValidationError("A lot is consumed or quarantined, never deleted.")

    @property
    def acquisition_cost(self):
        return self.unit_cost * self.quantity


# ============================================================
# Movements
# ============================================================

class MovementReason(models.TextChoices):
    RECEIPT = "receipt", "Received from supplier"
    RESERVATION = "reservation", "Reserved for an order"
    RELEASE = "release", "Reservation released"
    DISPATCH = "dispatch", "Dispatched"
    DELIVERY = "delivery", "Delivered"
    INSTALLATION = "installation", "Installed"
    CONSUMPTION = "consumption", "Consumed on a job"
    RETURN = "return", "Returned"
    QUARANTINE = "quarantine", "Quarantined"
    CORRECTION = "correction", "Counted correction"


class StockMovement(models.Model):
    """
    Append-only record of every physical change.

    Exactly one of unit or lot is set. A movement is never edited or
    deleted: a miscount is corrected by a further movement, so the
    history shows what was believed as well as what was true.
    """

    unit = models.ForeignKey(
        SerializedUnit, on_delete=models.PROTECT, null=True, blank=True,
        related_name="movements",
    )
    lot = models.ForeignKey(
        BatchLot, on_delete=models.PROTECT, null=True, blank=True,
        related_name="movements",
    )

    reason = models.CharField(max_length=20, choices=MovementReason.choices)
    from_status = models.CharField(max_length=20, choices=StockStatus.choices, blank=True)
    to_status = models.CharField(max_length=20, choices=StockStatus.choices)

    # Serialized movements are always one unit; a lot movement carries how
    # much moved, which is why this is not a count of rows.
    quantity = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("1.00"))

    order = models.ForeignKey(
        "orders.Order", on_delete=models.PROTECT, null=True, blank=True
    )
    note = models.TextField(blank=True)
    moved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="stock_movements"
    )
    moved_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-moved_at", "-id"]
        indexes = [
            models.Index(fields=["unit", "-moved_at"]),
            models.Index(fields=["lot", "-moved_at"]),
        ]
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(unit__isnull=False, lot__isnull=True)
                           | models.Q(unit__isnull=True, lot__isnull=False)),
                name="movement_names_one_stock_item",
            ),
        ]

    def __str__(self):
        subject = self.unit or self.lot
        return f"{subject} -> {self.to_status}"

    def save(self, *args, **kwargs):
        if self.pk:
            raise ValidationError("Stock movements are append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("Stock history cannot be deleted.")
