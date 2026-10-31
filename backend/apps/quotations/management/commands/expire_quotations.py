"""Record expired quotation states and audit events after the last valid business date."""

from django.core.management.base import BaseCommand
from apps.quotations.services import expire_quotes


class Command(BaseCommand):
    help = "Expire quotations whose validity ended before today in Asia/Kolkata."

    def handle(self, *args, **options):
        self.stdout.write(f"Expired {expire_quotes()} quotation(s).")
