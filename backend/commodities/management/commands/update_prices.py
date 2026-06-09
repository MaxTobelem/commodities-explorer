"""Daily price refresh (run from cron). Thin wrapper around services.update_prices."""

from django.core.management.base import BaseCommand, CommandError

from commodities import services
from commodities.models import ImportRun


class Command(BaseCommand):
    help = "Récupère et enregistre les derniers cours (USD/EUR) des matières actives."

    def handle(self, *args, **options):
        run = services.update_prices()
        if run.status == ImportRun.Status.ERROR:
            raise CommandError(run.message)
        self.stdout.write(self.style.SUCCESS(run.message))
