"""Backfill address matching keys and give incoming unowned enquiries a visible next action."""

from zoneinfo import ZoneInfo
from django.db import migrations
from django.utils import timezone


def backfill(apps, schema_editor):
    for site in apps.get_model("customers", "Site").objects.all().iterator():
        parts = (site.address_line, site.city, site.state, site.pincode)
        site.address_key = "|".join("".join(character for character in part.casefold() if character.isalnum()) for part in parts)
        site.save(update_fields=["address_key"])
    today = timezone.localdate(timezone=ZoneInfo("Asia/Kolkata"))
    apps.get_model("customers", "Enquiry").objects.filter(status="new", next_action="").update(
        next_action="Assign a sales owner and contact the customer", next_action_due=today,
    )


class Migration(migrations.Migration):
    dependencies = [("customers", "0003_enquiry_duplicate_review_and_more")]
    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
