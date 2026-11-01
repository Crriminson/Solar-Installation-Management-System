"""
What the assistant is allowed to know.

Two sources, both turned into sections and embedded by rebuild_index:

    knowledge/*.md   reviewed notes, one section per "## " heading
    the catalogue    products, packages, warranty policies, subsidy rules

The notes are written by people from sources they checked, not scraped
pages dropped in raw: a small model repeats whatever it is given, and the
sources disagree often enough that someone has to decide what to say.

Every staff role can ask the assistant anything, so nothing here may be
restricted to some of them. rules.md section 4 keeps purchase cost and
margin from Sales, so company_sections reads named fields only, never
ProductPrice, and no customer, order or staff record is touched.
"""

import hashlib
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.db import transaction

from apps.catalogue.models import (PackageTemplate, Product, QuantityBasis, VersionStatus,
                                   WarrantyPolicy)
from apps.core.api import business_date
from apps.subsidies.calculation import calculate_amount
from apps.subsidies.models import SchemeVersion

from . import ollama
from .models import KnowledgeChunk

KNOWLEDGE_DIR = Path(__file__).parent / "knowledge"

# Prefixes nomic-embed-text was trained with. Search uses the other one.
DOCUMENT_PREFIX = "search_document: "

EMBED_BATCH_SIZE = 16

COMPANY_TITLE = "Our catalogue"

# The sizes we sell, spelled out on each subsidy rule.
SUBSIDY_SIZES_KW = (1, 2, 3, 4, 5)


@dataclass(frozen=True)
class Section:
    document: str
    title: str
    heading: str
    text: str
    source_url: str
    checked_on: date

    @property
    def searchable_text(self):
        return f"{DOCUMENT_PREFIX}{self.title}: {self.heading}\n{self.text}"

    @property
    def content_hash(self):
        fingerprint = f"{settings.ASSISTANT_EMBED_MODEL}\n{self.searchable_text}"
        return hashlib.sha256(fingerprint.encode()).hexdigest()


# ============================================================
# Reading the notes
# ============================================================

def parse_note(path):
    """
    Splits one note into sections.

    A file opens with title and checked lines between --- markers. A
    "Source: <url>" line inside a section says where that section came
    from, and a "source:" line in the header is the default for the file.
    """
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines or lines[0].strip() != "---":
        raise ValueError(f"{path.name} has no header")

    end = lines.index("---", 1)
    header = dict(line.split(": ", 1) for line in lines[1:end])
    checked_on = date.fromisoformat(header["checked"])

    sections = []
    heading, body, source = None, [], ""

    def finish():
        if heading is not None:
            sections.append(Section(
                document=path.stem, title=header["title"], heading=heading,
                text="\n".join(body).strip(), source_url=source or header.get("source", ""),
                checked_on=checked_on,
            ))

    for line in lines[end + 1:]:
        if line.startswith("## "):
            finish()
            heading, body, source = line[3:].strip(), [], ""
        elif line.startswith("Source: "):
            source = line[len("Source: "):].strip()
        else:
            body.append(line)
    finish()
    return sections


def note_sections():
    return [section for path in sorted(KNOWLEDGE_DIR.glob("*.md")) for section in parse_note(path)]


# ============================================================
# Reading the catalogue
# ============================================================

def company_section(heading, text, source_url=""):
    return Section(document="company-catalogue", title=COMPANY_TITLE, heading=heading,
                   text=text, source_url=source_url, checked_on=business_date())


def describe_product(product):
    facts = [f"{product.name} (SKU {product.sku})"]
    if product.rated_power_w:
        facts.append(f"{product.rated_power_w:f} W")
    if product.storage_kwh:
        facts.append(f"{product.storage_kwh:f} kWh")
    if product.nominal_voltage_v:
        facts.append(f"{product.nominal_voltage_v:f} V")
    if product.warranty_policy:
        facts.append(f"warranty policy: {product.warranty_policy.name}")
    return ", ".join(facts)


def product_sections():
    products = Product.objects.filter(is_active=True).select_related("warranty_policy")
    by_category = {}
    for product in products:
        by_category.setdefault(product.get_category_display(), []).append(product)

    return [
        company_section(f"{category} we sell",
                        "\n".join(f"- {describe_product(product)}" for product in group))
        for category, group in by_category.items()
    ]


def describe_line(line):
    if line.basis == QuantityBasis.FIXED:
        return f"- {line.quantity:f} {line.product.unit} of {line.product.name}"
    return f"- {line.product.name}, {line.get_basis_display().lower()}"


def package_sections():
    sections = []
    templates = PackageTemplate.objects.prefetch_related("versions__lines__product")
    for template in templates:
        version = next((version for version in template.versions.all()
                        if version.status == VersionStatus.ACTIVE), None)
        if version:
            lines = "\n".join(describe_line(line) for line in version.lines.all())
            sections.append(company_section(
                f"What is in the {template.name} package",
                f"Version {version.version_number} of {template.name} contains:\n{lines}",
            ))
    return sections


def warranty_sections():
    sections = []
    for policy in WarrantyPolicy.objects.all():
        replacement = ("A replacement gets a full new term." if policy.fresh_period_on_replacement
                       else "A replacement keeps the original expiry date.")
        conditions = f" Conditions: {policy.conditions}" if policy.conditions else ""
        sections.append(company_section(
            f"Warranty policy: {policy.name}",
            f"The {policy.name} policy runs {policy.duration_months} months from delivery. "
            f"{replacement}{conditions}",
        ))
    return sections


def describe_subsidy(rule):
    formula = rule.calculation
    method = formula["method"]
    if method == "slabs":
        lower, parts = 0, []
        for slab in formula["slabs"]:
            parts.append(f"Rs {slab['rate']} per kW from {lower} to {slab['up_to_kw']} kW")
            lower = slab["up_to_kw"]
        amount = "; ".join(parts)
    elif method == "per_kw":
        amount = f"Rs {formula['rate']} per kW"
    elif method == "per_kwh":
        amount = f"Rs {formula['amount']} per unit generated"
    else:
        amount = f"Rs {formula['amount']} fixed"
    if formula.get("cap"):
        amount += f", capped at Rs {formula['cap']}"
    return amount


def worked_amounts(rule):
    """
    The amount at each size, from the estimator quotations use. A small
    model gets "Rs 15,000 per kW, capped at Rs 30,000" wrong, and the
    assistant must never disagree with a quotation.
    """
    if rule.calculation["method"] not in ("per_kw", "slabs"):
        return ""
    amounts = [f"{size} kW system: Rs {calculate_amount(rule.calculation, Decimal(size)):,.0f}"
               for size in SUBSIDY_SIZES_KW]
    return f" Amounts: {'; '.join(amounts)}."


def subsidy_sections():
    """The newest version of each scheme in force, as the estimator picks it."""
    today = business_date()
    rules = SchemeVersion.objects.filter(is_active=True, effective_from__lte=today).order_by(
        "scheme", "-effective_from", "-version", "-id")

    sections, seen = [], set()
    for rule in rules:
        if rule.scheme in seen or (rule.effective_until and rule.effective_until <= today):
            continue
        seen.add(rule.scheme)
        where = rule.jurisdiction or "All India (central)"
        conditions = f" Conditions: {', '.join(rule.conditions)}." if rule.conditions else ""
        sections.append(company_section(
            f"Subsidy rule: {rule.scheme}",
            f"{rule.scheme} ({where}), our quotation rule for {rule.customer_type} "
            f"{rule.system_type} systems: {describe_subsidy(rule)}."
            f"{worked_amounts(rule)}{conditions} Source quality: {rule.provenance}",
            source_url=rule.source_url,
        ))
    return sections


def company_sections():
    return [*product_sections(), *package_sections(), *warranty_sections(), *subsidy_sections()]


# ============================================================
# Building the index
# ============================================================

def embed_all(sections):
    vectors = []
    for start in range(0, len(sections), EMBED_BATCH_SIZE):
        batch = sections[start:start + EMBED_BATCH_SIZE]
        vectors.extend(ollama.embed([section.searchable_text for section in batch]))
    return vectors


def rebuild_index():
    """
    Brings the index in line with the notes and the catalogue.

    Embeds first and writes after, so a server that dies halfway leaves
    the old index answering rather than half of a new one.
    """
    sections = [*note_sections(), *company_sections()]
    stored = {(chunk.document, chunk.heading): chunk.content_hash
              for chunk in KnowledgeChunk.objects.only("document", "heading", "content_hash")}

    changed = [section for section in sections
               if stored.get((section.document, section.heading)) != section.content_hash]
    vectors = embed_all(changed)
    current = {(section.document, section.heading) for section in sections}

    with transaction.atomic():
        stale = [key for key in stored if key not in current]
        for document, heading in stale:
            KnowledgeChunk.objects.filter(document=document, heading=heading).delete()

        for section, vector in zip(changed, vectors):
            KnowledgeChunk.objects.update_or_create(
                document=section.document, heading=section.heading,
                defaults={
                    "title": section.title, "text": section.text,
                    "source_url": section.source_url, "checked_on": section.checked_on,
                    "content_hash": section.content_hash, "embedding": vector,
                },
            )

    return {"sections": len(sections), "embedded": len(changed), "removed": len(stale)}
