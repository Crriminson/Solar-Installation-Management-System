"""
Loads the agreed starting values from spec.md section 14.

They are data so they can be edited without a code change. Warranty
durations are configuration from the brief, not manufacturer terms.
"""

from django.db import migrations

WARRANTY_POLICIES = [
    ("Inverter and battery", 24),
    ("Panel", 240),
]


def load_defaults(apps, schema_editor):
    apps.get_model("catalogue", "SizingDefaults").objects.create(
        cable_waste_factor="1.15", cable_termination_buffer_m="5.00"
    )

    policy = apps.get_model("catalogue", "WarrantyPolicy")
    for name, duration_months in WARRANTY_POLICIES:
        policy.objects.create(name=name, duration_months=duration_months)


class Migration(migrations.Migration):
    dependencies = [("catalogue", "0001_initial")]

    operations = [migrations.RunPython(load_defaults, migrations.RunPython.noop)]
