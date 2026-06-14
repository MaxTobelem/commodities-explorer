"""Refresh commodity news events — publisher RSS + Google News (for a daily cron).

    python manage.py refresh_events

Pulls market news from curated publisher feeds with real summaries — French
(presse, energy/agri) and English (mining, metals) — and fills the uncovered
commodities via Google News. Lighter than ``enrich_data`` (which also re-pulls the
annual USGS/OWID/RMIS data), so it can run daily to keep the news feed current.
"""

from django.core.management.base import BaseCommand, CommandError

from commodities import services
from commodities.models import ImportRun


class Command(BaseCommand):
    help = "Rafraîchit les actualités (presse FR + mining EN + repli Google News, cron quotidien)."

    def handle(self, *args, **options):
        run = services.refresh_events()
        if run.status == ImportRun.Status.ERROR:
            raise CommandError(run.message)
        self.stdout.write(self.style.SUCCESS(run.message))
