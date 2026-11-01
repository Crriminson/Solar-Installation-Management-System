"""
Builds a demonstration of the whole business on an empty database.

    POSTGRES_DB=solar_demo manage.py migrate
    POSTGRES_DB=solar_demo manage.py seed_demo [--labels labels.pdf]

It reads like six months of a real installer's ERP: customers across
India, on-grid and off-grid systems from 1 to 5 kW, monthly restocking,
completed installations with their payments and costs, lost leads,
a cancelled order, repairs under warranty. On top of that history it
leaves one customer waiting at every stage, so a presenter can walk the
lifecycle live.

Every business record is made through the application's own API, as
the staff member whose job it is, so the demo obeys every rule the
screens do: permissions, stock movements, warranties, audit history.
Only staff accounts are created directly, as an administrator would in
Django admin. Spec.md section 14 asks that the demonstration use normal
application actions; this is that, scripted.

The past is replayed rather than backdated. While a past step runs,
django.utils.timezone.now answers with the moment that step happened,
so everything the application derives from "now" (invoice dates,
warranty start and expiry, audit history, business dates) comes out as
it would have on that day. Nothing is edited afterwards.

It refuses a database that already holds enquiries, so demo customers
never mix with real ones, and runs in one transaction: a failure part-way
leaves nothing behind.

In the demo database only, the dummy packages are taken live by the demo
administrator and the products get realistic generic names (D073).
seed_catalogue on its own never does either (D028).
"""

import io
from contextlib import contextmanager
from datetime import timedelta, timezone as dt_timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image, ImageDraw

from apps.accounts.models import Role
from apps.catalogue.models import (PackageTemplate, PackageVersion, Product, TrackingMethod,
                                   WarrantyPolicy)
from apps.core.api import business_date
from apps.customers.models import QUALIFICATION_CHECKS, Enquiry
from apps.inventory.labels import labels_for_order, labels_pdf
from apps.inventory.models import BatchLot, SerializedUnit, StockStatus, Supplier
from apps.orders.models import Order
from apps.scheduling.models import Job, JobKind
from apps.support.models import ServiceTicket

User = get_user_model()
JSON = "application/json"
DEFAULT_PASSWORD = "demo-pass-123"
BUSINESS_ZONE = ZoneInfo(settings.BUSINESS_TIMEZONE)

INSTALL_HOURS = 6             # a demo installation, start to finish
VISIT_HOURS = 2               # a service visit
OFF_GRID_LOAD_KW = "1.20"     # critical load an off-grid survey records
OFF_GRID_BACKUP_HOURS = "4.0"


# ============================================================
# Who works here
# ============================================================

# username, first name, surname, roles, hourly cost rate in INR
STAFF = [
    ("demo_admin", "Demo", "Administrator", [Role.ADMINISTRATOR], None),
    ("director_sanjay", "Sanjay", "Kapoor", [Role.DIRECTOR], None),
    ("sales_anita", "Anita", "Sharma", [Role.SALES], None),
    ("sales_rohan", "Rohan", "Mehta", [Role.SALES], None),
    ("ops_meera", "Meera", "Iyer", [Role.OPERATIONS_MANAGER], None),
    ("tech_ravi", "Ravi", "Kumar", [Role.TECHNICIAN], "400.00"),
    ("tech_suresh", "Suresh", "Patil", [Role.TECHNICIAN], "350.00"),
    ("tech_imran", "Imran", "Shaikh", [Role.TECHNICIAN], "350.00"),
    ("tech_deepa", "Deepa", "Nair", [Role.TECHNICIAN], "375.00"),
    ("wh_karan", "Karan", "Singh", [Role.WAREHOUSE], None),
    ("support_neha", "Neha", "Joshi", [Role.SUPPORT], None),
    ("fin_arjun", "Arjun", "Rao", [Role.FINANCE], None),
]

SUPPLIERS = [
    ("Suryakiran Modules Pvt Ltd", "Vikram Desai", "9800000001"),
    ("Volta Power Electronics", "Pooja Kulkarni", "9800000002"),
    ("Shakti Cables and Switchgear", "Sameer Khan", "9800000003"),
]

# Realistic generic names for the dummy catalogue, in the demo database
# only. No brands: these describe the part, not a manufacturer.
PRODUCT_NAMES = {
    "PNL-540": "540 Wp mono PERC half-cut panel",
    "INV-3K": "3 kW on-grid string inverter (legacy)",
    "INV-3K-OFF": "3 kW off-grid inverter (legacy)",
    "BAT-2K4": "2.4 kWh LFP battery, 24 V",
    "CTR-40A": "40 A MPPT charge controller",
    "MNT-RAIL": "Galvanised mounting structure set",
    "CBL-DC4": "4 mm² solar DC cable, UV rated",
    "CBL-AC4": "4 mm² copper AC cable",
    "CON-MC4": "MC4 connector pair, IP67",
    "PRT-MCB": "AC/DC distribution box with SPD and MCB",
    "ERT-KIT": "Earthing kit with chemical electrode",
    "SVC-INSTALL": "Installation and commissioning, per system",
    "SVC-HOUR": "Service technician, per hour",
    **{f"DEMO-INV-{kw}K-on_grid": f"{kw} kW on-grid string inverter" for kw in range(1, 6)},
    **{f"DEMO-INV-{kw}K-off_grid": f"{kw} kW off-grid hybrid inverter" for kw in range(1, 6)},
}
PRODUCT_DESCRIPTION = "Prices in this demonstration are illustrative."
PACKAGE_NOTES = "Standard bill of materials for this system size. Prices are illustrative."


def package_name(template):
    """What the demo calls each package: what a customer would be sold."""
    kw = f"{template.capacity_kw.normalize():f}" if template.capacity_kw else ""
    return {
        "on_grid": f"On-grid rooftop system, {kw} kW",
        "off_grid": f"Off-grid system with battery backup, {kw} kW",
        "panel_set": "Solar panel set",
        "installation": "Installation service",
    }.get(template.kind, template.name)

INVERTERS = [f"DEMO-INV-{kw}K-{grid}" for kw in range(1, 6) for grid in ("on_grid", "off_grid")]

# (days ago, supplier, [(sku, quantity)]): the first delivery stocks the
# warehouse, later ones top it up the way a monthly reorder would.
DELIVERIES = [
    (178, "Suryakiran Modules Pvt Ltd", [("PNL-540", 220)]),
    (178, "Volta Power Electronics", [*[(sku, 6) for sku in INVERTERS],
                                      ("BAT-2K4", 24), ("CTR-40A", 8)]),
    (177, "Shakti Cables and Switchgear", [
        ("CBL-DC4", 2500), ("CBL-AC4", 2500), ("CON-MC4", 300),
        ("MNT-RAIL", 120), ("ERT-KIT", 40), ("PRT-MCB", 40)]),
    (96, "Suryakiran Modules Pvt Ltd", [("PNL-540", 120)]),
    (95, "Volta Power Electronics", [*[(sku, 3) for sku in INVERTERS], ("BAT-2K4", 12)]),
    (31, "Suryakiran Modules Pvt Ltd", [("PNL-540", 80)]),
    (30, "Volta Power Electronics", [*[(sku, 2) for sku in INVERTERS], ("CTR-40A", 4)]),
]


# ============================================================
# Customers
# ============================================================

def person(name, phone, address, city, state, pincode, kw, system="on_grid",
           kind="residential", note=""):
    return {"full_name": name, "phone": phone, "address_line": address, "city": city,
            "state": state, "pincode": pincode, "customer_type": kind,
            "requested_system_type": system, "requested_capacity_kw": kw, "notes": note}


# The last six months. Each runs from enquiry to its outcome, starting
# the given number of days ago. Starts are unique, so no technician is
# ever booked twice on one day.
HISTORY = [
    (176, "completed", person("Harish Bhat", "9845002001", "42 Kumara Park West", "Bengaluru",
                              "Karnataka", "560020", "3.00")),
    (168, "completed", person("Fatima Sheikh", "9820002002", "B-204 Hill View, Bandra West",
                              "Mumbai", "Maharashtra", "400050", "2.00")),
    (161, "lost", person("Manoj Tiwari", "9839002003", "18 Gomti Nagar", "Lucknow",
                         "Uttar Pradesh", "226010", "3.00"),
     "Chose a cheaper local installer."),
    (155, "completed", person("Gurpreet Kaur", "9814002004", "77 Model Town", "Ludhiana",
                              "Punjab", "141002", "5.00", kind="commercial",
                              note="Rooftop of a garment shop, power cuts in the afternoon.")),
    (147, "completed", person("Anand Krishnan", "9840002005", "9 Kotturpuram Main Road",
                              "Chennai", "Tamil Nadu", "600085", "3.00", "off_grid",
                              note="Farmhouse with unreliable grid; wants battery backup.")),
    (139, "completed", person("Neelam Chauhan", "9829002006", "C-55 Vaishali Nagar", "Jaipur",
                              "Rajasthan", "302021", "4.00")),
    (131, "lost", person("Sanjay Deshpande", "9822002007", "5 Shivaji Nagar", "Pune",
                         "Maharashtra", "411005", "2.00"),
     "Housing society did not approve roof use."),
    (124, "completed", person("Ritu Agarwal", "9831002008", "12 Ballygunge Place", "Kolkata",
                              "West Bengal", "700019", "3.00")),
    (116, "completed", person("Venkat Rao", "9849002009", "Plot 14, Madhapur", "Hyderabad",
                              "Telangana", "500081", "5.00", kind="commercial",
                              note="Small clinic; daytime load from air conditioning.")),
    (108, "completed", person("Sheela Pillai", "9847002010", "TC 22/1180 Kowdiar",
                              "Thiruvananthapuram", "Kerala", "695003", "2.00", "off_grid")),
    (100, "lost", person("Dinesh Yadav", "9826002011", "31 Saket Nagar", "Indore",
                         "Madhya Pradesh", "452018", "3.00"),
     "Postponed: waiting for the subsidy portal to reopen."),
    (92, "completed", person("Pooja Bansal", "9810002012", "E-17 Greater Kailash II",
                             "New Delhi", "Delhi", "110048", "4.00")),
    (84, "completed", person("Mohammed Irfan", "9825002013", "Near Lal Darwaja, Relief Road",
                             "Ahmedabad", "Gujarat", "380001", "3.00", kind="commercial")),
    (76, "cancelled", person("Kiran Joshi", "9823002014", "11 Gangapur Road", "Nashik",
                             "Maharashtra", "422013", "3.00"),
     "Customer is relocating to another city."),
    (68, "completed", person("Arvind Menon", "9846002015", "Kadavanthra Road", "Kochi",
                             "Kerala", "682020", "5.00"), "loss"),
    (60, "completed", person("Swati Mishra", "9835002016", "Ashok Rajpath", "Patna",
                             "Bihar", "800004", "2.00")),
    (52, "lost", person("Prakash Gowda", "9844002017", "Vijayanagar 2nd Stage", "Mysuru",
                        "Karnataka", "570017", "1.00"),
     "Rented home; owner declined."),
    (44, "completed", person("Rohit Sharma", "9826001012", "9 Vijay Nagar", "Indore",
                             "Madhya Pradesh", "452010", "3.00")),
    (36, "completed", person("Lakshmi Menon", "9845001013", "27 Indiranagar 100 Ft Road",
                             "Bengaluru", "Karnataka", "560038", "3.00"), "loss"),
    (33, "completed", person("Nikhil Kulkarni", "9822002019", "Dhantoli", "Nagpur",
                             "Maharashtra", "440012", "3.00")),
]

# Waiting today, one per stage.
TODAY = {
    "priya": person("Priya Nair", "9847001001", "14 Marine Drive", "Kochi", "Kerala", "682031",
                    "3.00", note="Wants a lower bill before summer."),
    "arjun": person("Arjun Reddy", "9848001002", "Plot 22, Jubilee Hills", "Hyderabad",
                    "Telangana", "500033", "3.00"),
    "kavita": person("Kavita Joshi", "9822001003", "7 Law College Road", "Pune",
                     "Maharashtra", "411004", "2.00"),
    "rahul": person("Rahul Verma", "9829001004", "B-12 Malviya Nagar", "Jaipur",
                    "Rajasthan", "302017", "3.00"),
    "sneha": person("Sneha Kulkarni", "9823001005", "5 College Road", "Nashik",
                    "Maharashtra", "422005", "4.00"),
    "imran": person("Imran Qureshi", "9839001006", "21 Hazratganj", "Lucknow",
                    "Uttar Pradesh", "226001", "3.00"),
    "meena": person("Meena Iyer", "9840001007", "3 Besant Avenue, Adyar", "Chennai",
                    "Tamil Nadu", "600020", "2.00"),
    "deepak": person("Deepak Singh", "9826001008", "45 Arera Colony", "Bhopal",
                     "Madhya Pradesh", "462016", "3.00"),
    "anjali": person("Anjali Gupta", "9825001009", "11 C G Road", "Ahmedabad", "Gujarat",
                     "380009", "3.00"),
    "vikram": person("Vikram Malhotra", "9810001010", "D-4 Vasant Vihar", "New Delhi",
                     "Delhi", "110057", "5.00"),
    "sunita": person("Sunita Patil", "9822001011", "18 Dharampeth", "Nagpur",
                     "Maharashtra", "440010", "3.00"),
}

# A job is loss-making when this lands on it: crane and scaffolding for a
# tall roof. Sized to sink one job without sinking the business.
LOSS_EXPENSE = ("Crane hire and scaffolding for a four-storey roof", "60000.00")
SMALL_EXPENSE = ("Transport of materials to site", "1800.00")


# ============================================================
# The command
# ============================================================

class Command(BaseCommand):
    help = "Builds six months of demo history plus a customer waiting at every stage."

    def add_arguments(self, parser):
        parser.add_argument("--password", default=DEFAULT_PASSWORD,
                            help="Password for every demo account.")
        parser.add_argument("--labels", metavar="PDF",
                            help="Also save the barcode labels for the order ready to scan.")

    def handle(self, *args, **options):
        if Enquiry.objects.exists() or Order.objects.exists():
            raise CommandError(
                "This database already has enquiries. seed_demo only builds on an empty "
                "one, so demo customers never mix with real ones. Use a fresh database, "
                "for example POSTGRES_DB=solar_demo, migrate it, then run this again."
            )

        demo = Demo(options["password"], self.stdout)
        with transaction.atomic(), patch("django.utils.timezone.now", demo.clock):
            demo.build()

        if options["labels"]:
            path = Path(options["labels"])
            labels = labels_for_order(demo.ready_to_scan)
            path.write_bytes(labels_pdf(labels, f"Stock labels {demo.ready_to_scan.reference}"))
            self.stdout.write(f"  {len(labels)} labels for {demo.ready_to_scan.reference} "
                              f"saved to {path.resolve()}")

        self.stdout.write(self.style.SUCCESS(demo.summary()))


class Clock:
    """
    Stands in for django.utils.timezone.now while the past is replayed.

    Outside a replayed step it answers with the real time. Inside one it
    answers with that step's moment, a second later at each reading, so
    events within a step keep their order. Always in UTC, as the real
    one does: a quotation's content hash includes its issue time as text,
    and it must read the same after a trip through the database.
    """

    def __init__(self):
        self.real_now = timezone.now
        self.moment = None

    def __call__(self):
        if self.moment is None:
            return self.real_now()
        self.moment += timedelta(seconds=1)
        return self.moment

    def day(self, days_ago, hour):
        """That day, at that hour of the business's own clock."""
        today = self.real_now().astimezone(BUSINESS_ZONE)
        return (today - timedelta(days=days_ago)).replace(
            hour=hour, minute=0, second=0, microsecond=0)

    @contextmanager
    def at(self, days_ago, hour=11):
        self.moment = self.day(days_ago, hour).astimezone(dt_timezone.utc)
        try:
            yield self.moment
        finally:
            self.moment = None


class Demo:
    """Plays each role in turn, through the API, on the day it happened."""

    def __init__(self, password, out):
        self.password = password
        self.out = out
        self.client = Client(HTTP_HOST="localhost")
        self.clock = Clock()
        self.key = 0
        self.completed = []

    # --- plumbing -----------------------------------------------------

    def call(self, user, name, args=(), data=None, *, method="post", multipart=False):
        """One request as one person. Anything but success stops the build."""
        if user is None:
            self.client.logout()
        else:
            self.client.force_login(user)
        url = reverse(name, args=args)
        send = getattr(self.client, method)
        if method == "get":
            response = send(url)
        elif multipart:
            response = send(url, data or {})
        else:
            response = send(url, data or {}, content_type=JSON)
        if response.status_code >= 300:
            raise CommandError(f"{method.upper()} {url} as {user}: {response.status_code} "
                               f"{response.content[:600]!r}")
        return response.json() if response.content else None

    def idempotency(self, label):
        self.key += 1
        return f"demo-{label}-{self.key}"

    def say(self, text):
        self.out.write(f"  {text}")

    # --- the build ----------------------------------------------------

    def build(self):
        with self.clock.at(180, 9):
            self.staff()
            self.catalogue()
        self.history()
        self.pipeline()
        self.orders()
        self.support()

    def staff(self):
        self.people = {}
        for username, first, last, roles, _rate in STAFF:
            # The administrator is also a Django superuser: seed_catalogue
            # records one as the catalogue's author, and the presenter can
            # add staff in Django admin.
            make = (User.objects.create_superuser if Role.ADMINISTRATOR in roles
                    else User.objects.create_user)
            self.people[username] = make(
                username, password=self.password, first_name=first, last_name=last,
                roles=[role.value for role in roles])
        self.admin, self.director = self.people["demo_admin"], self.people["director_sanjay"]
        self.sales, self.ops = self.people["sales_anita"], self.people["ops_meera"]
        self.warehouse, self.support_desk = self.people["wh_karan"], self.people["support_neha"]
        self.finance = self.people["fin_arjun"]
        self.crew = [self.people[name] for name in ("tech_ravi", "tech_suresh", "tech_imran",
                                                     "tech_deepa")]
        self.rates = {self.people[name]: Decimal(rate) for name, *_, rate in STAFF if rate}

        for technician, rate in self.rates.items():
            self.call(self.finance, "technician-rates", data={
                "technician": technician.pk, "rate_per_hour": str(rate),
                "effective_from": str(business_date() - timedelta(days=30))})
        self.say(f"{len(STAFF)} staff accounts, technician rates set")

    def catalogue(self):
        call_command("seed_catalogue", stdout=io.StringIO())
        policy = WarrantyPolicy.objects.get(name="Inverter and battery")
        for product in Product.objects.all():
            changes = {"description": PRODUCT_DESCRIPTION}
            if product.sku in PRODUCT_NAMES:
                changes["name"] = PRODUCT_NAMES[product.sku]
            # The dummy inverters carry no policy, but the demo sells "two
            # years on inverters": warranties are copied at delivery (F12).
            if product.sku.startswith("DEMO-INV-") and product.warranty_policy_id is None:
                changes["warranty_policy"] = policy.pk
            self.call(self.admin, "product-detail", [product.pk],
                      {"revision": product.revision, **changes}, method="patch")
        # No screen edits a package's name, so the demo renames these
        # setup records directly; nothing depends on the text (D073).
        for template in PackageTemplate.objects.all():
            template.name = package_name(template)
            template.save(update_fields=["name"])
        # Notes change while the versions are still drafts, through the
        # API; once live a version is locked for good (F04).
        for version in PackageVersion.objects.filter(status="draft").order_by("id"):
            version = self.call(self.admin, "version-detail", [version.pk], {
                "revision": version.revision, "notes": PACKAGE_NOTES}, method="patch")
            # Reviewed in the demo only: see the module docstring.
            self.call(self.admin, "version-activate", [version["id"]],
                      {"revision": version["revision"]})
        for name, contact, phone in SUPPLIERS:
            self.call(self.warehouse, "supplier-list", data={
                "name": name, "contact_name": contact, "phone": phone})
        self.say("catalogue with realistic names, packages live, 3 suppliers")

    # --- purchasing ---------------------------------------------------

    def restock(self, supplier_name, items, *, paid):
        """Raise, place and receive a purchase order; invoice and pay it."""
        supplier = Supplier.objects.get(name=supplier_name)
        lines = []
        for sku, quantity in items:
            product = Product.objects.get(sku=sku)
            lines.append({"product": product.pk, "quantity": str(quantity),
                          "unit_cost": str(product.current_price().purchase_cost_excl_tax)})
        purchase = self.call(self.warehouse, "purchase-create",
                             data={"supplier": supplier.pk, "lines": lines})
        purchase = self.call(self.warehouse, "purchase-place", [purchase["id"]],
                             {"revision": purchase["revision"]})
        rows = []
        for line in purchase["lines"]:
            quantity = int(Decimal(line["quantity"]))
            if line["tracking_method"] == TrackingMethod.SERIALIZED:
                prefix = f"SN{purchase['id']:02d}-{line['sku'].replace('DEMO-', '')}"
                rows.append({"line": line["id"], "serial_numbers": [
                    f"{prefix}-{index:04d}" for index in range(1, quantity + 1)]})
            else:
                rows.append({"line": line["id"], "quantity": str(quantity),
                             "batch_id": f"LOT{purchase['id']:02d}-{line['sku']}"})
        self.call(self.warehouse, "purchase-receive", [purchase["id"]],
                  {"received_on": str(business_date()), "lines": rows,
                   "delivery_note_reference": f"DN/{supplier.pk}/{purchase['id']:03d}"})

        total = sum(Decimal(line["quantity"]) * Decimal(line["unit_cost"]) for line in lines)
        gross = (total * Decimal("1.12")).quantize(Decimal("1.00"))
        self.call(self.finance, "supplier-invoice", [purchase["id"]],
                  {"reference": f"INV/{supplier.pk}/{purchase['id']:04d}", "amount": str(gross)})
        if paid:
            self.call(self.finance, "supplier-payments", data={
                "purchase_order": purchase["id"], "amount": str(gross),
                "paid_on": str(business_date()), "reference": f"RTGS/{purchase['id']:05d}"})

    # --- one customer, step by step ------------------------------------

    def enquiry(self, payload, *, web=False, source="phone"):
        if web:
            reply = self.call(None, "enquiry-create", data=payload)
            return Enquiry.objects.get(reference=reply["reference"])
        reply = self.call(self.sales, "enquiry-create", data={**payload, "source": source})
        return Enquiry.objects.get(pk=reply["id"])

    def assign(self, enquiry, owner=None, *, due=None, action="Call the customer"):
        enquiry.refresh_from_db()
        self.call(owner or self.sales, "enquiry-assign", [enquiry.pk], {
            "owner": (owner or self.sales).pk, "revision": enquiry.revision,
            "next_action": action, "next_action_due": str(due or business_date())}, method="patch")

    def contact(self, enquiry, summary, reached=True):
        self.call(self.sales, "enquiry-contacts", [enquiry.pk], {
            "channel": "phone", "summary": summary, "reached_customer": reached,
            "contacted_at": (timezone.now() - timedelta(minutes=30)).isoformat()})

    def move(self, enquiry, status, action="", **extra):
        enquiry.refresh_from_db()
        self.call(self.sales, "enquiry-status", [enquiry.pk], {
            "status": status, "revision": enquiry.revision, "next_action": action,
            "next_action_due": str(business_date() + timedelta(days=1)), **extra})

    def qualify(self, enquiry):
        self.move(enquiry, "qualified", "Request the site survey",
                  qualification_checks={check: True for check in QUALIFICATION_CHECKS},
                  reason="Usable roof, steady consumption, grid connection suitable.")

    def start_survey(self, enquiry, technician):
        survey = self.call(self.sales, "survey-start", data={"enquiry": enquiry.pk})
        survey = self.call(self.ops, "survey-assign", [survey["id"]],
                           {"assigned_to": technician.pk, "revision": survey["revision"]})
        self.move(enquiry, "survey_scheduled", "Wait for the survey report")
        return survey

    def capture_survey(self, survey, technician, payload):
        off_grid = payload["requested_system_type"] == "off_grid"
        revision = self.call(technician, "revision-create", [survey["id"]], {
            "surveyed_at": (timezone.now() - timedelta(hours=3)).isoformat(),
            "roof_type": "flat_rcc", "roof_length_m": "12.00", "roof_width_m": "9.00",
            "usable_area_sqm": "60.00", "orientation": "S", "tilt_degrees": "15.0",
            "cable_distance_m": "22.50", "recommended_system_type": payload["requested_system_type"],
            "recommended_capacity_kw": payload["requested_capacity_kw"],
            **({"critical_load_kw": OFF_GRID_LOAD_KW,
                "backup_duration_hours": OFF_GRID_BACKUP_HOURS} if off_grid else {}),
            "notes": "Roof in good condition. Light shading from a water tank after 4 pm.",
        })
        self.call(technician, "revision-photos", [revision["id"]],
                  {"image": picture("roof.png", f"Roof, {payload['city']}"),
                   "caption": "South face of the roof"}, multipart=True)
        return self.call(technician, "revision-submit", [revision["id"]],
                         {"revision": revision["revision"]})

    def approve_survey(self, revision):
        self.call(self.ops, "revision-review", [revision["id"]], {
            "decision": "approved", "revision": revision["revision"],
            "notes": "Measurements consistent with the photos."})

    def generate_quote(self, enquiry, plan="advance"):
        return self.call(self.sales, "quotation-generate", data={
            "enquiry": enquiry.pk, "idempotency_key": self.idempotency("gen"),
            "payment_plan": plan})

    def issue_quote(self, quote):
        return self.call(self.sales, "quotation-action", [quote["id"], "issue"], {
            "revision": quote["revision"], "idempotency_key": self.idempotency("issue")})

    def accept_quote(self, quote, payload):
        self.call(self.sales, "quotation-accept", [quote["id"]], {
            "revision": quote["revision"], "idempotency_key": self.idempotency("accept"),
            "customer_name": payload["full_name"],
            "signature": picture("signature.png", payload["full_name"])}, multipart=True)

    def confirm(self, quote):
        reply = self.call(self.sales, "order-confirm", data={"quotation": quote["id"]})
        return Order.objects.get(pk=reply["id"])

    def pay(self, order, amount, reference, method="bank_transfer"):
        self.call(self.finance, "payment-create", [order.pk], {
            "kind": "receipt", "amount": str(amount), "method": method,
            "external_reference": reference, "status": "cleared",
            "paid_on": str(business_date())})

    def pack(self, order):
        fulfilment = self.call(self.warehouse, "fulfilment-open", data={"order": order.pk})
        if fulfilment["status"] != "reserved":
            raise CommandError(f"{order.reference} could not be reserved: "
                               f"{fulfilment['blocked_reason'] or fulfilment['status']}")
        for unit in SerializedUnit.objects.filter(order=order, status=StockStatus.RESERVED):
            self.call(self.warehouse, "fulfilment-scan", [fulfilment["id"]],
                      {"code": unit.asset_id})
        for lot in BatchLot.objects.filter(order=order, status=StockStatus.RESERVED):
            self.call(self.warehouse, "fulfilment-scan", [fulfilment["id"]],
                      {"code": lot.batch_id, "quantity": str(lot.quantity)})
        fulfilment = self.call(self.warehouse, "fulfilment-detail", [fulfilment["id"]],
                               method="get")
        fulfilment = self.call(self.warehouse, "fulfilment-close", [fulfilment["id"]],
                               {"revision": fulfilment["revision"]})
        return self.call(self.warehouse, "fulfilment-dispatch", [fulfilment["id"]],
                         {"revision": fulfilment["revision"],
                          "carrier_reference": f"MH-12-TC-{4000 + order.pk}"})

    def deliver(self, order, fulfilment):
        self.call(self.warehouse, "fulfilment-deliver", [fulfilment["id"]], {
            "revision": fulfilment["revision"], "delivered_at": timezone.now().isoformat(),
            "received_by_name": order.customer.full_name})

    def book(self, order, technician, start):
        job = Job.objects.get(order=order, kind=JobKind.INSTALLATION)
        self.call(self.ops, "job-action", [job.pk, "schedule"], {
            "revision": job.revision, "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=INSTALL_HOURS)).isoformat(),
            "technicians": [technician.pk],
            "notes": "Ladder access from the side gate. Call the customer on arrival."})
        job.refresh_from_db()
        return job

    def install(self, order, job, technician, payload):
        """On site: start, record the evidence, and the customer signs."""
        self.call(self.ops, "job-action", [job.pk, "start"], {"revision": job.revision})
        report = self.call(technician, "installation-open", data={"job": job.pk})
        finished = timezone.now() - timedelta(minutes=30)
        kw = Decimal(payload["requested_capacity_kw"])
        report = self.call(technician, "installation-update", [report["id"]], {
            "revision": report["revision"],
            "started_at": (finished - timedelta(hours=INSTALL_HOURS)).isoformat(),
            "finished_at": finished.isoformat(),
            "system_type": payload["requested_system_type"],
            "installed_capacity_kw": str(kw),
            "checklist": [{"item": check, "passed": True} for check in report["mandatory_checks"]],
            "generation_test_kw": str((kw * Decimal("0.88")).quantize(Decimal("0.01"))),
            "generation_test_passed": True,
            "generation_test_notes": "Clear sky at midday; output within the expected range.",
            "notes": "Customer shown the isolator and the monitoring app."})
        for unit in SerializedUnit.objects.filter(order=order, status=StockStatus.DELIVERED):
            self.call(technician, "installation-units", [report["id"]],
                      {"code": unit.asset_id, "position": "South array"})
        self.call(technician, "installation-photos", [report["id"]],
                  {"image": picture("array.png", f"Array, {payload['city']}"),
                   "caption": "Finished array from the south"}, multipart=True)
        report = self.call(technician, "installation-detail", [report["id"]], method="get")
        report = self.call(technician, "installation-submit", [report["id"]],
                           {"revision": report["revision"]})
        self.call(technician, "installation-decide", [report["id"]], {
            "decision": "accepted", "document_revision": report["revision"],
            "customer_name": payload["full_name"],
            "signature": picture("signature.png", payload["full_name"])}, multipart=True)
        self.call(technician, "time-entries", data={
            "job": job.pk, "hours": str(INSTALL_HOURS), "work_date": str(business_date())})

    # --- the last six months --------------------------------------------

    def history(self):
        deliveries = list(DELIVERIES)
        last_purchase = deliveries[-1]
        for index, (days_ago, outcome, payload, *extra) in enumerate(HISTORY):
            # Restock before the customers that need it.
            while deliveries and deliveries[0][0] >= days_ago:
                when, supplier, items = deliveries.pop(0)
                with self.clock.at(when, 11):
                    self.restock(supplier, items, paid=(when, supplier, items) != last_purchase)
            technician = self.crew[index % len(self.crew)]
            if outcome == "lost":
                self.lost(days_ago, payload, extra[0])
            elif outcome == "cancelled":
                self.cancelled(days_ago, payload, technician, extra[0])
            else:
                self.completed_job(days_ago, payload, technician, loss=bool(extra))
        while deliveries:
            when, supplier, items = deliveries.pop(0)
            with self.clock.at(when, 11):
                self.restock(supplier, items, paid=(when, supplier, items) != last_purchase)
        self.say(f"history: {len(self.completed)} completed installations, "
                 f"{sum(1 for row in HISTORY if row[1] == 'lost')} lost enquiries, "
                 "a cancelled order, monthly restocking over six months")

    def lost(self, d, payload, reason):
        with self.clock.at(d, 10):
            enquiry = self.enquiry(payload, web=True)
        with self.clock.at(d - 1, 12):
            self.assign(enquiry)
            self.contact(enquiry, "Discussed the roof and the monthly bill.")
            self.move(enquiry, "contacting", "Send a rough estimate")
        with self.clock.at(d - 4, 16):
            self.contact(enquiry, reason)
            self.move(enquiry, "lost", reason=reason)

    def sold(self, d, payload, technician, source="phone"):
        """Enquiry to confirmed order, over the first two weeks."""
        with self.clock.at(d, 10):
            enquiry = self.enquiry(payload, source=source)
        with self.clock.at(d - 1, 11):
            self.assign(enquiry)
            self.contact(enquiry, "Spoke to the customer about their roof and their bill.")
            self.move(enquiry, "contacting", "Confirm roof access and the latest bill")
        with self.clock.at(d - 2, 15):
            self.qualify(enquiry)
        with self.clock.at(d - 3, 10):
            survey = self.start_survey(enquiry, technician)
        with self.clock.at(d - 6, 14):
            revision = self.capture_survey(survey, technician, payload)
        with self.clock.at(d - 7, 10):
            self.approve_survey(revision)
        with self.clock.at(d - 8, 12):
            quote = self.issue_quote(self.generate_quote(enquiry))
        with self.clock.at(d - 12, 17):
            self.accept_quote(quote, payload)
            return self.confirm(quote)

    def completed_job(self, d, payload, technician, *, loss):
        """The whole lifecycle, over about a month."""
        order = self.sold(d, payload, technician)
        with self.clock.at(d - 13, 12):
            self.pay(order, order.advance_payable, f"NEFT{order.pk:04d}A", "upi")
        with self.clock.at(d - 18, 10):
            fulfilment = self.pack(order)
        with self.clock.at(d - 19, 14):
            self.deliver(order, fulfilment)
        with self.clock.at(d - 20, 9):
            job = self.book(order, technician, self.clock.day(d - 22, 9))
        with self.clock.at(d - 22, 16):
            self.install(order, job, technician, payload)
            expense = LOSS_EXPENSE if loss else SMALL_EXPENSE
            self.call(self.finance, "expenses", data={
                "order": order.pk, "description": expense[0], "amount_excl_tax": expense[1],
                "incurred_on": str(business_date())})
        with self.clock.at(d - 23, 11):
            order.refresh_from_db()
            balance = self.call(self.finance, "order-balance-invoice", [order.pk])
        with self.clock.at(d - 27, 13):
            self.pay(order, balance["outstanding"], f"NEFT{order.pk:04d}B")
        with self.clock.at(d - 30, 17):
            self.call(self.finance, "technician-payments", data={
                "technician": technician.pk,
                "amount": str(self.rates[technician] * INSTALL_HOURS),
                "paid_on": str(business_date()), "reference": f"SAL/{order.pk:04d}"})
        order.refresh_from_db()
        self.completed.append((order, loss, d))

    def cancelled(self, d, payload, technician, reason):
        order = self.sold(d, payload, technician)
        with self.clock.at(d - 13, 12):
            self.pay(order, order.advance_payable, f"NEFT{order.pk:04d}A")
        with self.clock.at(d - 16, 15):
            order.refresh_from_db()
            self.call(self.sales, "order-cancel", [order.pk],
                      {"revision": order.revision, "reason": reason})
        with self.clock.at(d - 17, 11):
            # The advance goes back as a refund; nothing is erased.
            self.call(self.finance, "payment-create", [order.pk], {
                "kind": "refund", "amount": str(order.advance_payable), "method": "bank_transfer",
                "external_reference": f"REFUND{order.pk:04d}", "status": "cleared",
                "paid_on": str(business_date())})

    # --- waiting today ----------------------------------------------------

    def pipeline(self):
        priya = self.enquiry(TODAY["priya"], web=True)
        self.enquiry(TODAY["arjun"], web=True)
        # Assigned, but the call is a day late: shows up as overdue.
        overdue = self.enquiry(TODAY["kavita"], source="referral")
        self.assign(overdue, self.people["sales_rohan"],
                    due=business_date() - timedelta(days=1), action="Call back about the bill")
        self.contact(priya, "Rang twice, no answer. Will try in the evening.", reached=False)

        rahul = self.enquiry(TODAY["rahul"])
        self.assign(rahul)
        self.move(rahul, "contacting", "Confirm roof access")
        self.qualify(rahul)
        self.start_survey(rahul, self.crew[0])

        sneha = self.enquiry(TODAY["sneha"])
        self.assign(sneha)
        self.move(sneha, "contacting", "Confirm roof access")
        self.qualify(sneha)
        self.capture_survey(self.start_survey(sneha, self.crew[1]), self.crew[1], TODAY["sneha"])

        quotes = {}
        for key, technician in (("imran", self.crew[2]), ("meena", self.crew[3]),
                                ("deepak", self.crew[0])):
            enquiry = self.enquiry(TODAY[key])
            self.assign(enquiry)
            self.move(enquiry, "contacting", "Confirm roof access")
            self.qualify(enquiry)
            revision = self.capture_survey(self.start_survey(enquiry, technician), technician,
                                           TODAY[key])
            self.approve_survey(revision)
            quotes[key] = self.generate_quote(enquiry)
        self.issue_quote(quotes["meena"])
        self.accept_quote(self.issue_quote(quotes["deepak"]), TODAY["deepak"])
        self.say("today: 3 new enquiries, a survey to capture, one to approve, a draft, "
                 "an issued and an accepted quotation")

    def today_order(self, key, technician):
        enquiry = self.enquiry(TODAY[key])
        self.assign(enquiry)
        self.move(enquiry, "contacting", "Confirm roof access")
        self.qualify(enquiry)
        revision = self.capture_survey(self.start_survey(enquiry, technician), technician,
                                       TODAY[key])
        self.approve_survey(revision)
        quote = self.issue_quote(self.generate_quote(enquiry))
        self.accept_quote(quote, TODAY[key])
        return self.confirm(quote)

    def orders(self):
        self.unpaid = self.today_order("anjali", self.crew[1])

        self.ready_to_scan = self.today_order("vikram", self.crew[2])
        self.pay(self.ready_to_scan, self.ready_to_scan.advance_payable, "NEFT-VM-1101")
        self.book(self.ready_to_scan, self.crew[2], self.clock.day(-3, 10))

        self.ready_to_install = self.today_order("sunita", self.crew[3])
        self.pay(self.ready_to_install, self.ready_to_install.advance_payable, "NEFT-SP-1102")
        self.deliver(self.ready_to_install, self.pack(self.ready_to_install))
        self.book(self.ready_to_install, self.crew[1], self.clock.day(-1, 10))
        self.say("today: one order unpaid, one paid and ready to scan, one delivered with "
                 "its installation booked for tomorrow")

    # --- after-sales ------------------------------------------------------

    def ticket(self, order, unit, fault):
        reply = self.call(self.support_desk, "ticket-raise", data={
            "customer": order.customer_id, "units": [unit.pk], "fault_description": fault})
        return ServiceTicket.objects.get(pk=reply["id"])

    def act(self, ticket, action, actor=None, **body):
        ticket.refresh_from_db()
        return self.call(actor or self.support_desk, "ticket-action", [ticket.pk, action],
                         {"revision": ticket.revision, **body})

    def visit(self, ticket, technician, start):
        reply = self.call(self.ops, "ticket-visit", [ticket.pk], {
            "starts_at": start.isoformat(),
            "ends_at": (start + timedelta(hours=VISIT_HOURS)).isoformat(),
            "technicians": [technician.pk]})
        return reply["id"]

    def covered_repair(self, order, unit, technician, days_ago, fault, findings):
        """Raised, visited, fixed under warranty and confirmed, over a week."""
        with self.clock.at(days_ago, 10):
            ticket = self.ticket(order, unit, fault)
            visit = self.visit(ticket, technician, self.clock.day(days_ago - 2, 15))
        with self.clock.at(days_ago - 2, 16):
            self.act(ticket, "diagnose", technician, job=visit, findings=findings,
                     recommendation="Replace the faulty part.")
            self.act(ticket, "start-work", technician)
            self.act(ticket, "work-line", technician, asset=ticket.assets.get().pk,
                     product=Product.objects.get(sku="CON-MC4").pk, quantity="1")
            self.act(ticket, "finish", technician)
        with self.clock.at(days_ago - 4, 11):
            self.act(ticket, "confirm", customer_name=order.customer.full_name)

    def support(self):
        jobs = sorted(self.completed, key=lambda row: -row[2])
        first, middle = jobs[0][0], jobs[len(jobs) // 2][0]
        latest_loss = [order for order, loss, _ in jobs if loss][-1]
        latest = jobs[-1][0]

        def unit(order, category):
            return SerializedUnit.objects.filter(order=order, product__category=category).first()

        self.covered_repair(first, unit(first, "panel"), self.crew[0], 120,
                            "One panel string reads zero output.",
                            "MC4 connector on string 2 burnt out.")
        self.covered_repair(middle, unit(middle, "panel"), self.crew[1], 40,
                            "Output dropped by a third over a week.",
                            "Loose MC4 connector on the second string.")

        # New today, in warranty: the support desk takes it from here.
        self.ticket(latest, unit(latest, "inverter"),
                    "Inverter display shows error E-21 every morning.")

        # Not covered: physical damage, an estimate waiting on the customer.
        damaged = self.ticket(latest_loss, unit(latest_loss, "panel"),
                              "Panel glass cracked after a storm.")
        damaged.refresh_from_db()
        self.call(self.ops, "ticket-review", [damaged.pk], {
            "revision": damaged.revision, "asset": damaged.assets.get().pk,
            "assessment": "not_covered",
            "reason": "Impact damage from a falling branch is outside the warranty conditions."})
        # Diagnosed on a visit that has happened, not one still to come.
        visit = self.visit(damaged, self.crew[0], self.clock.day(2, 15))
        self.act(damaged, "diagnose", self.crew[0], job=visit,
                 findings="Front glass shattered; cells exposed.",
                 recommendation="Replace the panel.")
        self.act(damaged, "estimate", lines=[
            {"product": Product.objects.get(sku="PNL-540").pk, "quantity": "1"},
            {"product": Product.objects.get(sku="SVC-HOUR").pk, "quantity": "2"}])
        self.loss = latest_loss
        self.say("support: repairs closed under warranty in the past, a new fault today, "
                 "and an uncovered repair waiting for the customer's approval")

    # --- what to show --------------------------------------------------

    def summary(self):
        return "\n".join([
            "",
            "Demo ready. Every account uses the password: " + self.password,
            "  demo_admin       everything      director_sanjay  dashboard",
            "  sales_anita      sales           ops_meera        surveys, schedule",
            "  wh_karan         warehouse       tech_suresh      tomorrow's installation",
            "  support_neha     tickets         fin_arjun        payments",
            "",
            "Six months of history behind it: open the dashboard with a custom range",
            "covering the last six months to see the trends.",
            "",
            "Where each stage waits today:",
            "  Enquiries     new web enquiries (Priya, Arjun), an overdue call (Kavita)",
            "  Surveys       Rahul to capture (tech_ravi), Sneha to approve",
            "  Quotations    Imran draft, Meena issued, Deepak accepted: confirm the order",
            f"  Orders        {self.unpaid.reference} unpaid, "
            f"{self.ready_to_scan.reference} paid: scan it at Packing (Print labels there)",
            f"  Schedule      {self.ready_to_install.reference} installs tomorrow (tech_suresh)",
            f"  Dashboard     {len(self.completed)} completed jobs; {self.loss.reference} lost money "
            "to crane hire",
            "  Tickets       a new fault, an estimate awaiting the customer, past repairs closed",
            "  Labels        Purchasing > a purchase order > Print labels, or Packing > Print labels",
        ])


# ============================================================
# Pictures
# ============================================================

def picture(name, label):
    """A small real PNG, so uploads pass the same checks a photo does."""
    image = Image.new("RGB", (320, 200), (232, 238, 246))
    ImageDraw.Draw(image).text((16, 90), label, fill=(15, 23, 42))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    buffer.name = name
    return buffer
