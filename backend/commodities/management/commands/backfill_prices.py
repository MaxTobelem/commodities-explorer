"""Backfill historical prices via Commodities-API time series.

    uv run python manage.py backfill_prices --days 180
"""

from django.core.management.base import BaseCommand, CommandError

from commodities import services
from commodities.models import ImportRun


class Command(BaseCommand):
    help = "Backfill l'historique des cours (Commodities-API timeseries)."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=90, help="Profondeur de l'historique en jours.")

    def handle(self, *args, **options):
        run = services.backfill_prices(days=options["days"])
        if run.status == ImportRun.Status.ERROR:
            raise CommandError(run.message)
        self.stdout.write(self.style.SUCCESS(run.message))
