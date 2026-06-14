"""Backfill recent DAILY prices from Commodities-API (fills the World Bank → today gap).

    python manage.py backfill_daily --days 30
    python manage.py backfill_daily --days 196 --missing   # only newly-mapped tickers

Cost: /timeseries is capped at ~30 days/request, so depth is fetched in 30-day
windows — ~1 API request per symbol per 30 days of depth (+ EUR). Use --missing to
fetch only commodities whose daily history doesn't reach back that far, so re-runs
don't re-spend quota on data already ingested.
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
        parser.add_argument(
            "--missing",
            action="store_true",
            help="Ne traiter que les matières dont l'historique quotidien ne remonte pas "
            "jusqu'à --days (les nouveaux tickers), pour ne pas redépenser de quota.",
        )

    def handle(self, *args, **options):
        run = services.backfill_daily(days=options["days"], missing=options["missing"])
        if run.status == ImportRun.Status.ERROR:
            raise CommandError(run.message)
        self.stdout.write(self.style.SUCCESS(run.message))
