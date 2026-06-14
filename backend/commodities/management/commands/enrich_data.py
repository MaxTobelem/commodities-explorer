"""Monthly enrichment (run from cron). Wrapper around services.enrich_data."""

from django.core.management.base import BaseCommand, CommandError

from commodities import services
from commodities.models import ImportRun


class Command(BaseCommand):
    help = "Importe réserves/production (USGS), secteurs/produits (RMIS) et actualités (presse/mining/Google)."

    def handle(self, *args, **options):
        run = services.enrich_data()
        if run.status == ImportRun.Status.ERROR:
            raise CommandError(run.message)
        self.stdout.write(self.style.SUCCESS(run.message))
