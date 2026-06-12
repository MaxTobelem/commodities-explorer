"""Backfill recent DAILY prices from Commodities-API (fills the World Bank → today gap).

    python manage.py backfill_daily --days 30

Cost: /timeseries is capped at ~30 days/request, so depth is fetched in 30-day
windows — roughly 23 API requests (22 symbols + EUR) per 30 days of depth.
"""

from django.core.management.base import BaseCommand, CommandError

from commodities import services
from commodities.models import ImportRun


class Command(BaseCommand):
    help = "Backfill les cours quotidiens récents (Commodities-API) pour combler le trou WB→aujourd'hui."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days",
            type=int,
            default=30,
            help="Profondeur du backfill en jours (fenêtres de 30 j ≈ 23 requêtes API / 30 j).",
        )

    def handle(self, *args, **options):
        run = services.backfill_daily(days=options["days"])
        if run.status == ImportRun.Status.ERROR:
            raise CommandError(run.message)
        self.stdout.write(self.style.SUCCESS(run.message))
