"""
Stock labels (F08, F09): a printable barcode for every unit and batch.

Spec.md F08 is how "scan every item" is done honestly: each unit and each
batch is scanned at the identity its physical form supports. A label is
that identity in a form a scanner reads. The barcode holds exactly what
the packing scan box accepts: a unit's asset ID, a batch's batch code.

Code 128, because every USB and Bluetooth keyboard-wedge scanner reads it
and it carries letters, digits and hyphens. Four labels to an A4 page,
one under another, each wide enough for a phone camera to read easily.
"""

import io

from django.db.models import Sum
from reportlab.graphics import renderPDF
from reportlab.graphics.barcode import createBarcodeDrawing
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from .models import BatchLot, SerializedUnit

LABELS_PER_PAGE = 4
PAGE_MARGIN = 12 * mm
LABEL_GAP = 6 * mm
BARCODE_HEIGHT = 22 * mm
BAR_WIDTH = 0.42 * mm         # the narrowest bar; wider reads more reliably
TEXT_INSET = 6 * mm


def unit_label(unit):
    """What one serialized unit's label says."""
    receipt = unit.goods_receipt
    return {
        "code": unit.asset_id,
        "title": unit.product.name,
        "lines": [
            f"{unit.product.sku}  ·  Serial {unit.serial_number or 'none'}",
            f"Received {receipt.received_on:%d %b %Y}  ·  {receipt.reference}  ·  "
            f"{receipt.purchase_order.reference}",
        ],
    }


def lot_label(lot, quantity=None):
    """
    What one batch's label says.

    A batch splits as parts of it are reserved, and every part keeps the
    batch code. Pass the quantity to print: as received for the receiving
    label, or the part being packed for an order.
    """
    receipt = lot.goods_receipt
    amount = lot.quantity if quantity is None else quantity
    return {
        "code": lot.batch_id,
        "title": lot.product.name,
        "lines": [
            f"{lot.product.sku}  ·  Batch of {amount.normalize():f} {lot.unit}",
            f"Received {receipt.received_on:%d %b %Y}  ·  {receipt.reference}  ·  "
            f"{receipt.purchase_order.reference}",
        ],
    }


def labels_for_purchase(purchase):
    """
    Every unit and batch as it arrived on one purchase order.

    One label per batch as delivered: its first part, carrying the
    quantity of every part split from it since.
    """
    units = (SerializedUnit.objects.filter(goods_receipt__purchase_order=purchase)
             .select_related("product", "goods_receipt__purchase_order").order_by("product__sku", "id"))
    lots = (BatchLot.objects.filter(goods_receipt__purchase_order=purchase, parent_lot__isnull=True)
            .annotate(split_off=Sum("portions__quantity"))
            .select_related("product", "goods_receipt__purchase_order").order_by("product__sku", "id"))
    return ([unit_label(unit) for unit in units]
            + [lot_label(lot, lot.quantity + (lot.split_off or 0)) for lot in lots])


def labels_for_order(order):
    """What is held for one customer order, for the packing bench."""
    units = (SerializedUnit.objects.filter(order=order)
             .select_related("product", "goods_receipt__purchase_order").order_by("product__sku", "id"))
    lots = (BatchLot.objects.filter(order=order)
            .select_related("product", "goods_receipt__purchase_order").order_by("product__sku", "id"))
    return [unit_label(unit) for unit in units] + [lot_label(lot) for lot in lots]


def labels_pdf(labels, heading):
    """The labels as an A4 PDF, four to a page, in the order given."""
    buffer = io.BytesIO()
    page = canvas.Canvas(buffer, pagesize=A4)
    page.setTitle(heading)
    width, height = A4
    slot = (height - 2 * PAGE_MARGIN - (LABELS_PER_PAGE - 1) * LABEL_GAP) / LABELS_PER_PAGE

    for index, label in enumerate(labels):
        position = index % LABELS_PER_PAGE
        if index and position == 0:
            page.showPage()
        top = height - PAGE_MARGIN - position * (slot + LABEL_GAP)
        _draw_label(page, label, PAGE_MARGIN, top - slot, width - 2 * PAGE_MARGIN, slot)

    if not labels:
        page.setFont("Helvetica", 11)
        page.drawString(PAGE_MARGIN, height - PAGE_MARGIN - 11, "Nothing to label.")
    page.save()
    return buffer.getvalue()


def _draw_label(page, label, left, bottom, width, height):
    # A thin border shows where to cut, or matches a label stock's outline.
    page.setLineWidth(0.5)
    page.roundRect(left, bottom, width, height, 3 * mm)

    text_left = left + TEXT_INSET
    line = bottom + height - TEXT_INSET - 4 * mm
    page.setFont("Helvetica-Bold", 13)
    page.drawString(text_left, line, label["title"][:70])

    page.setFont("Helvetica", 9.5)
    for text in label["lines"]:
        line -= 5.5 * mm
        page.drawString(text_left, line, text[:110])

    # The code is printed under the bars by hand rather than by the barcode
    # library, whose text crowds the bars at this size: a person must be
    # able to read it when the scanner cannot.
    code_height = 5 * mm
    barcode = createBarcodeDrawing("Code128", value=label["code"], barWidth=BAR_WIDTH,
                                   barHeight=BARCODE_HEIGHT, humanReadable=False)
    renderPDF.draw(barcode, page, text_left, bottom + TEXT_INSET + code_height)
    page.setFont("Courier-Bold", 12)
    page.drawCentredString(text_left + barcode.width / 2, bottom + TEXT_INSET, label["code"])
