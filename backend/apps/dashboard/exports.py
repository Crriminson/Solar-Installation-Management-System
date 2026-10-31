"""
Dashboard exports (F15): tables as CSV, the summary as PDF.

Both state the period and filters they represent, so a file passed
around later still says what it covers.
"""

import csv
import io
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from apps.core.api import business_date

from .metrics import COUNT, GROUPS, HOURS, MONEY, card

# A spreadsheet runs a cell starting with these as a formula, and customer
# names reach this file from a public form.
FORMULA_PREFIXES = ("=", "+", "-", "@", "\t", "\r")

# Thousands, then every two digits: 12,34,567.
INDIAN_FIRST_GROUP = 3
INDIAN_GROUP = 2

PAGE_MARGIN_POINTS = 36
HEADER_GREY = colors.HexColor("#f5f5f4")
RULE_GREY = colors.HexColor("#d6d3d1")


def safe_cell(value):
    """Neutralises a text cell that a spreadsheet would execute."""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return business_date(value).isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    text = str(value)
    return f"'{text}" if text.startswith(FORMULA_PREFIXES) else text


def generated_stamp():
    """In business time. Django's own zone is UTC, so localtime alone would lie."""
    moment = timezone.localtime(timezone.now(), ZoneInfo(settings.BUSINESS_TIMEZONE))
    return f"Generated {moment:%d %b %Y, %H:%M} IST"


def metric_csv(metric, filters):
    """One filtered table, with its period stamped above the header."""
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow([metric.label])
    writer.writerow(["Period", filters.description])
    writer.writerow(["Generated", timezone.now().isoformat()])
    writer.writerow([])
    writer.writerow(["Reference", "Name", "Detail", "Date", "Amount"])
    for row in metric.rows(filters):
        writer.writerow([safe_cell(row[key]) for key in
                         ("reference", "label", "detail", "date", "amount")])
    return buffer.getvalue()


def indian_number(value):
    """1234567.50 as 12,34,567.50. The PDF's fonts have no rupee sign."""
    sign = "-" if value < 0 else ""
    whole, _point, fraction = f"{abs(value):.2f}".partition(".")

    head, tail = whole[:-INDIAN_FIRST_GROUP], whole[-INDIAN_FIRST_GROUP:]
    groups = []
    while head:
        groups.insert(0, head[-INDIAN_GROUP:])
        head = head[:-INDIAN_GROUP]
    return sign + ",".join([*groups, tail]) + f".{fraction}"


def formatted(value, kind):
    if kind == MONEY:
        return f"INR {indian_number(value)}"
    if kind == HOURS:
        return f"{value} h"
    return str(value) if kind == COUNT else value


def summary_pdf(filters):
    """Every figure, grouped as on screen, with the period at the top."""
    buffer = io.BytesIO()
    document = SimpleDocTemplate(
        buffer, pagesize=A4, title="Director summary",
        leftMargin=PAGE_MARGIN_POINTS, rightMargin=PAGE_MARGIN_POINTS,
        topMargin=PAGE_MARGIN_POINTS, bottomMargin=PAGE_MARGIN_POINTS,
    )
    styles = getSampleStyleSheet()
    story = [
        Paragraph("Director summary", styles["Title"]),
        Paragraph(filters.description, styles["Normal"]),
        Paragraph(generated_stamp(), styles["Normal"]),
        Spacer(1, 12),
    ]

    for title, metrics in GROUPS:
        rows = [[title, "", ""]]
        for metric in metrics:
            figure = card(metric, filters)
            rows.append([metric.label, formatted(figure["value"], metric.kind), metric.caption])
        story.append(_summary_table(rows))
        story.append(Spacer(1, 10))

    document.build(story)
    return buffer.getvalue()


def _summary_table(rows):
    table = Table(rows, colWidths=[170, 120, 233])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), HEADER_GREY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 1), (1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, -1), 0.25, RULE_GREY),
    ]))
    return table
