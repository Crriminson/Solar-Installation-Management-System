"""Seed editable quotation terms agreed in spec section 14."""

from django.db import migrations


def seed_defaults(apps, schema_editor):
    apps.get_model("quotations", "QuotationSettings").objects.create(
        pk=1, validity_days=30, advance_default_percent="30.00",
        advance_min_percent="20.00", advance_max_percent="100.00",
    )


class Migration(migrations.Migration):
    dependencies = [("quotations", "0001_initial")]
    operations = [migrations.RunPython(seed_defaults, migrations.RunPython.noop)]
