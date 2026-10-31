"""F02 qualification confirmations and outcome reason, separate from F01 duplicate review."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("customers", "0004_address_keys_and_followups")]
    operations = [
        migrations.AddField(model_name="enquiry", name="qualification_checks", field=models.JSONField(blank=True, default=dict)),
        migrations.AddField(model_name="enquiry", name="qualification_reason", field=models.TextField(blank=True)),
    ]
