"""
Turning a record into a PDF.

Every builder reads a frozen snapshot where the record has one, so the
same input always produces the same paper. Nothing here reaches for a
live price, a current address or today's catalogue.

Amounts print as "INR 1,20,500.00". The built-in fonts have no rupee
sign, and an inserted box glyph would be worse than the three letters.
"""

import io
from decimal import Decimal

from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.api import business_date

PAGE_MARGIN_POINTS = 36
CELL_FONT_SIZE = 8
HEADER_GREY = colors.HexColor("#eef2f7")
RULE_GREY = colors.HexColor("#cbd5e1")

# Thousands, then every two digits: 12,34,567.
INDIAN_FIRST_GROUP = 3
INDIAN_GROUP = 2


# ============================================================
# Formatting
# ============================================================

def indian_number(value):
    """1234567.5 -> 12,34,567.50"""
    quantised = Decimal(str(value)).quantize(Decimal("0.01"))
    whole, _, fraction = f"{abs(quantised):.2f}".partition(".")
    if len(whole) > INDIAN_FIRST_GROUP:
        head, tail = whole[:-INDIAN_FIRST_GROUP], whole[-INDIAN_FIRST_GROUP:]
        groups = []
        while len(head) > INDIAN_GROUP:
            head, group = head[:-INDIAN_GROUP], head[-INDIAN_GROUP:]
            groups.insert(0, group)
        whole = ",".join([head, *groups, tail]) if head else ",".join([*groups, tail])
    sign = "-" if quantised < 0 else ""
    return f"{sign}{whole}.{fraction}"


def money(value):
    return f"INR {indian_number(value)}"


def generated_stamp():
    moment = timezone.localtime(timezone.now())
    return f"Generated {moment:%d %b %Y, %I:%M %p} IST"


# ============================================================
# Page scaffolding
# ============================================================

def _cell_style():
    style = getSampleStyleSheet()["BodyText"]
    style.fontSize = CELL_FONT_SIZE
    style.leading = CELL_FONT_SIZE + 2
    style.spaceBefore = 0
    style.spaceAfter = 0
    return style


_CELL_STYLE = _cell_style()


def _page(title):
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, title=title,
        leftMargin=PAGE_MARGIN_POINTS, rightMargin=PAGE_MARGIN_POINTS,
        topMargin=PAGE_MARGIN_POINTS, bottomMargin=PAGE_MARGIN_POINTS,
    )
    return buffer, document


def _facts(rows):
    table = Table([[label, value] for label, value in rows], colWidths=[150, 373])
    table.setStyle(TableStyle([
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("TEXTCOLOR", (0, 0), (0, -1), colors.HexColor("#475569")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    return table


# A plain string in a table cell does not wrap: ReportLab draws it on
# one line and lets it run over its neighbour. Anything that can be long
# goes in a Paragraph, which wraps inside the column.
def _cell(value):
    return Paragraph(str(value), _CELL_STYLE)


def _lines_table(header, rows, widths):
    wrapped = [
        [_cell(value) if index < 2 else value for index, value in enumerate(row)]
        for row in rows
    ]
    table = Table([header, *wrapped], colWidths=widths, repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE_GREY),
    ]))
    return table


# ============================================================
# Quotation (F05, F19)
# ============================================================

def quotation_pdf(content):
    """
    Built from `quotations.services.document_content`, which is the same
    frozen dictionary the content hash is taken over. Passing the stored
    snapshot in rather than the live record is what makes a regenerated
    quotation identical to the original.
    """
    snapshot = content["snapshot"]
    customer = snapshot["customer"]
    site = snapshot["site"]
    styles = getSampleStyleSheet()
    buffer, document = _page(f"Quotation {content['reference']}")

    story = [
        Paragraph("Quotation", styles["Title"]),
        Paragraph(
            f"{content['reference']} &#183; revision {content['revision_number']}",
            styles["Normal"],
        ),
        Paragraph(generated_stamp(), styles["Normal"]),
        Spacer(1, 12),
        _facts([
            ("Customer", customer["name"]),
            ("Phone", customer["phone"]),
            ("Site", f"{site['address']}, {site['city']}, {site['state']} {site['pincode']}"),
            ("Package", f"{snapshot['package']['name']} v{snapshot['package']['version']}"),
            ("Valid until", content["valid_until"]),
        ]),
        Spacer(1, 12),
    ]

    rows = [
        [line["sku"], line["description"],
         f"{line['quantity']} {line['unit']}",
         indian_number(line["unit_price_excl_tax"]),
         f"{line['gst_rate_percent']}%",
         indian_number(line["gross_incl_tax"])]
        for line in content["lines"]
    ]
    story.append(_lines_table(
        ["SKU", "Item", "Quantity", "Unit price", "GST", "Total incl. GST"],
        rows, [96, 158, 58, 62, 38, 70],
    ))
    story.append(Spacer(1, 10))

    story.append(_facts([
        ("Subtotal excluding GST", money(content["subtotal_excl_tax"])),
        ("GST", money(content["tax_amount"])),
        ("Gross payable including GST", money(content["gross_payable_incl_tax"])),
    ]))

    story.extend(_subsidy_block(content.get("subsidy") or [], styles))
    story.extend(_terms_block(content.get("terms") or {}, styles))

    story.append(Spacer(1, 10))
    story.append(Paragraph(snapshot.get("rounding", ""), styles["Italic"]))

    document.build(story)
    return buffer.getvalue()


def _subsidy_block(subsidy, styles):
    """
    Absent entirely when no rule applies (F17): no placeholder, no
    banner. Capital subsidy and a per-kWh incentive stay separate lines,
    because they are different things and must never be added together.
    """
    if not subsidy:
        return []

    # A capital subsidy and a per-kWh incentive are different things
    # and never become one number (spec.md F17).
    rows = [
        (entry.get("scheme", "Subsidy"),
         f"{money(entry['amount'])} {entry.get('unit', '')}".strip()
         if entry.get("rule_type") == "generation"
         else money(entry.get("amount", 0)))
        for entry in subsidy
    ]
    return [
        Spacer(1, 12),
        Paragraph("Estimated subsidy", styles["Heading3"]),
        _facts(rows),
        Paragraph(
            "Estimate only. Not an approval and not a disbursement. "
            "It does not reduce the gross payable above.",
            styles["Italic"],
        ),
    ]


def _terms_block(terms, styles):
    if not terms:
        return []

    rows = [("Payment plan", str(terms.get("plan", "")).replace("_", " "))]
    if terms.get("advance_amount_incl_tax"):
        rows.append(("Advance", money(terms["advance_amount_incl_tax"])))
    if terms.get("balance_amount_incl_tax"):
        rows.append(("Balance, due on delivery", money(terms["balance_amount_incl_tax"])))
    if terms.get("notes"):
        rows.append(("Notes", terms["notes"]))

    return [Spacer(1, 12), Paragraph("Payment terms", styles["Heading3"]), _facts(rows)]


# ============================================================
# Invoice and receipt (F07, F19)
# ============================================================

def invoice_pdf(invoice):
    """A demand for part of the order's value, including the zero-charge
    invoice warranty-covered work raises (spec.md F19)."""
    styles = getSampleStyleSheet()
    buffer, document = _page(f"Invoice {invoice.reference}")
    order = invoice.order
    customer = order.customer

    story = [
        Paragraph("Invoice", styles["Title"]),
        Paragraph(invoice.reference, styles["Normal"]),
        Paragraph(generated_stamp(), styles["Normal"]),
        Spacer(1, 12),
        _facts([
            ("Customer", customer.full_name),
            ("Phone", customer.phone),
            ("Order", order.reference),
            ("Invoice for", invoice.get_kind_display()),
            ("Issued", f"{timezone.localtime(invoice.issued_at):%d %b %Y}"
                       if invoice.issued_at else "-"),
        ]),
        Spacer(1, 12),
        _facts([
            ("Amount", money(invoice.amount)),
            ("Received so far", money(invoice.paid_amount)),
            ("Outstanding", money(invoice.amount - invoice.paid_amount)),
        ]),
    ]

    if invoice.amount == 0:
        story.append(Spacer(1, 10))
        story.append(Paragraph(
            "Covered under warranty. Nothing is payable on this invoice.",
            styles["Italic"],
        ))

    document.build(story)
    return buffer.getvalue()


def receipt_pdf(payment):
    """Acknowledges money actually received, against what it settled."""
    styles = getSampleStyleSheet()
    buffer, document = _page(f"Receipt {payment.pk}")
    order = payment.order
    paid_on = payment.paid_on if hasattr(payment, "paid_on") else None

    rows = [
        ("Customer", order.customer.full_name),
        ("Order", order.reference),
        ("Amount", money(payment.amount)),
        ("Method", payment.get_method_display()
         if hasattr(payment, "get_method_display") else payment.method),
        ("Reference", payment.external_reference or "-"),
        ("Payment date", f"{paid_on:%d %b %Y}" if paid_on else "-"),
    ]

    document.build([
        Paragraph("Payment receipt", styles["Title"]),
        Paragraph(generated_stamp(), styles["Normal"]),
        Spacer(1, 12),
        _facts(rows),
        Spacer(1, 10),
        Paragraph(
            "A receipt acknowledges money received. It is not a tax invoice.",
            styles["Italic"],
        ),
    ])
    return buffer.getvalue()


# ============================================================
# Installation handover (F11, F19)
# ============================================================

def handover_pdf(report):
    """
    What was installed, by serial, with the test result and the
    customer's acceptance. Spec.md F19: this is the document that
    settles "what did I actually get".
    """
    styles = getSampleStyleSheet()
    job = report.job
    order = job.order
    buffer, document = _page(f"Handover {order.reference}")
    acceptance = getattr(report, "acceptance", None)

    story = [
        Paragraph("Installation handover", styles["Title"]),
        Paragraph(order.reference, styles["Normal"]),
        Paragraph(generated_stamp(), styles["Normal"]),
        Spacer(1, 12),
        _facts([
            ("Customer", order.customer.full_name),
            ("Site", job.site.address_line),
            ("System", report.get_system_type_display() if report.system_type else "-"),
            ("Installed capacity",
             f"{report.installed_capacity_kw} kW" if report.installed_capacity_kw else "-"),
            ("Work finished",
             f"{timezone.localtime(report.finished_at):%d %b %Y, %I:%M %p}"
             if report.finished_at else "-"),
            ("Generation test",
             _test_result(report)),
        ]),
        Spacer(1, 12),
        Paragraph("Equipment installed", styles["Heading3"]),
    ]

    units = list(report.installed_units.select_related("unit", "unit__product"))
    if units:
        rows = [[installed.unit.asset_id,
                 installed.unit.serial_number or "-",
                 installed.unit.product.name]
                for installed in units]
        story.append(_lines_table(["Asset", "Serial", "Product"], rows, [110, 160, 212]))
    else:
        story.append(Paragraph("No serialised equipment recorded.", styles["Normal"]))

    story.append(Spacer(1, 12))
    story.append(Paragraph("Acceptance", styles["Heading3"]))
    if acceptance:
        story.append(_facts([
            ("Decision", acceptance.get_decision_display()),
            ("Name given", acceptance.customer_name),
            ("Decided", f"{timezone.localtime(acceptance.decided_at):%d %b %Y, %I:%M %p}"),
        ]))
        story.append(Paragraph(
            "Signed in the app as evidence of acceptance. Not an Aadhaar eSign "
            "or a certified digital signature.",
            styles["Italic"],
        ))
    else:
        story.append(Paragraph("Not yet accepted by the customer.", styles["Normal"]))

    document.build(story)
    return buffer.getvalue()


def _test_result(report):
    if report.generation_test_passed is None:
        return "-"
    outcome = "Passed" if report.generation_test_passed else "Failed"
    if report.generation_test_kw is not None:
        return f"{outcome} at {report.generation_test_kw} kW"
    return outcome


def today_stamp():
    return business_date()
