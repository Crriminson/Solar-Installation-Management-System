"""Subsidy arithmetic, eligibility, version dates and generation incentives remain separate."""

from datetime import timedelta
from decimal import Decimal
from django.test import TestCase
from django.core.exceptions import ValidationError
from rest_framework.exceptions import ValidationError as ApiValidationError

from apps.core.api import business_date
from apps.customers.models import Customer, Site
from apps.surveys.models import SurveyRevision
from .calculation import calculate_amount, estimate_subsidies
from .models import SchemeVersion


class SubsidyTests(TestCase):
    def setUp(self):
        customer = Customer.objects.create(full_name="Demo", phone="9000000000")
        self.site = Site.objects.create(customer=customer, address_line="1 Road", city="Delhi", state="Delhi", pincode="110001")
        self.survey = SurveyRevision(recommended_system_type="on_grid", recommended_capacity_kw=Decimal("3"))

    def test_central_slabs_are_incremental_and_capped(self):
        formula = {"method": "slabs", "slabs": [{"up_to_kw": "2", "rate": "30000"}, {"up_to_kw": "3", "rate": "18000"}], "cap": "78000"}
        for capacity, amount in (("1", "30000"), ("2", "60000"), ("2.5", "69000"), ("3", "78000"), ("5", "78000")):
            self.assertEqual(calculate_amount(formula, Decimal(capacity)), Decimal(amount))

    def test_delhi_capital_and_generation_are_different_rule_types(self):
        estimates = estimate_subsidies(self.site, self.survey, {})
        capital = [entry for entry in estimates if entry["rule_type"] == "capital"]
        generation = [entry for entry in estimates if entry["rule_type"] == "generation"]
        self.assertEqual(sum(Decimal(entry["amount"]) for entry in capital), Decimal("108000"))
        self.assertEqual(generation[0]["amount"], "3.00")
        self.assertEqual(generation[0]["unit"], "INR/kWh")

    def test_offgrid_and_commercial_are_not_eligible_for_residential_ongrid_rules(self):
        self.survey.recommended_system_type = "off_grid"
        self.assertEqual(estimate_subsidies(self.site, self.survey, {}), [])
        self.survey.recommended_system_type = "on_grid"
        self.site.customer.customer_type = "commercial"
        self.assertEqual(estimate_subsidies(self.site, self.survey, {}), [])

    def test_incomplete_states_get_central_only(self):
        for state in ("Haryana", "Chhattisgarh", "Assam", "Jharkhand", "Goa"):
            self.site.state = state
            estimates = estimate_subsidies(self.site, self.survey, {})
            self.assertEqual([entry["scheme"] for entry in estimates], ["PM Surya Ghar"])

    def test_required_category_does_not_guess_an_amount(self):
        self.site.state = "West Bengal"
        with self.assertRaises(ApiValidationError):
            estimate_subsidies(self.site, self.survey, {})
        estimates = estimate_subsidies(self.site, self.survey, {"sc_st_eligible": True})
        self.assertEqual(sum(Decimal(entry["amount"]) for entry in estimates), Decimal("108000"))

    def test_active_rule_is_immutable_and_latest_effective_version_wins(self):
        old = SchemeVersion.objects.get(scheme="Delhi capital top-up")
        with self.assertRaises(ValidationError):
            old.save()
        values = {field.name: getattr(old, field.name) for field in old._meta.fields
                  if field.name not in ("id", "created_at")}
        values.update(version=2, effective_from=business_date(), calculation={"method": "fixed", "amount": "12345"})
        SchemeVersion.objects.create(**values)
        entry = next(entry for entry in estimate_subsidies(self.site, self.survey, {}) if entry["scheme"] == old.scheme)
        self.assertEqual(entry["amount"], "12345.00")
        self.assertEqual(entry["version"], 2)

    def test_invalid_or_guessed_formula_is_rejected(self):
        rule = SchemeVersion.objects.get(scheme="Delhi capital top-up")
        for calculation in ({"method": "range", "amount": "15000-30000"}, {"method": "fixed", "amount": "NaN"}, {"method": "per_kw"}):
            rule.calculation = calculation
            with self.assertRaises(ValidationError):
                rule.clean()
