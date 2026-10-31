"""Load the owner's computable D026 register as dated data, with its recorded source quality."""

from django.db import migrations

BASELINE_DATE = "2026-10-31"
SECONDARY_SOURCE = "https://pmsolar.org.in/en/solar-subsidy-india/"
PROVENANCE = "Owner-approved D026 launch register. State figures are secondary-source estimates; official eligibility and disbursement are not guaranteed."


def seed_rules(apps, schema_editor):
    Rule = apps.get_model("subsidies", "SchemeVersion")
    shared = {"version": 1, "customer_type": "residential", "system_type": "on_grid",
              "effective_from": BASELINE_DATE, "last_checked": BASELINE_DATE,
              "source_url": SECONDARY_SOURCE, "provenance": PROVENANCE, "is_active": True,
              "rule_type": "capital", "required_documents": ["Electricity bill", "Identity and eligibility documents"]}
    Rule.objects.create(**{**shared, "scheme": "PM Surya Ghar", "authority": "MNRE", "jurisdiction": "",
                           "source_url": "https://solar.delhi.gov.in/page/central-subsidy",
                           "provenance": "Central residential slabs corroborated on the official Delhi Solar Portal on 31 Oct 2026.",
                           "calculation": {"method": "slabs", "slabs": [{"up_to_kw": "2", "rate": "30000"},
                                                                         {"up_to_kw": "3", "rate": "18000"}], "cap": "78000"}})
    rates = [("Delhi", "10000", "30000"), ("Uttar Pradesh", "15000", "30000"),
             ("West Bengal", "5000", "15000"), ("Bihar", "10000", "20000"),
             ("Ladakh", "20000", None), ("Jammu and Kashmir", "3000", None),
             ("Puducherry", "10000", "30000")]
    for jurisdiction, rate, cap in rates:
        Rule.objects.create(**shared, scheme=f"{jurisdiction} capital top-up", authority=jurisdiction,
                            jurisdiction=jurisdiction, calculation={"method": "per_kw", "rate": rate, "cap": cap})
    Rule.objects.create(**shared, scheme="Rajasthan beneficiary top-up", authority="Rajasthan", jurisdiction="Rajasthan",
                        conditions=["rajasthan_beneficiary"], calculation={"method": "fixed", "amount": "17000"})
    Rule.objects.create(**shared, scheme="West Bengal SC/ST top-up", authority="West Bengal", jurisdiction="West Bengal",
                        conditions=["sc_st_eligible"], calculation={"method": "fixed", "amount": "15000"})
    Rule.objects.create(**{**shared, "scheme": "Delhi generation incentive", "authority": "Delhi", "jurisdiction": "Delhi",
                           "rule_type": "generation", "calculation": {"method": "per_kwh", "amount": "3"}})


class Migration(migrations.Migration):
    dependencies = [("subsidies", "0001_initial")]
    operations = [migrations.RunPython(seed_rules, migrations.RunPython.noop)]
