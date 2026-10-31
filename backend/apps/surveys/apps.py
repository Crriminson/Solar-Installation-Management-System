"""App configuration for site surveys and their approval (F03)."""

from django.apps import AppConfig


class SurveysConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.surveys"
    label = "surveys"
