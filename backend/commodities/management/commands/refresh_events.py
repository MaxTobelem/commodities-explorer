"""Refresh commodity news events from Google News (for a daily cron).

    python manage.py refresh_events

Lighter than ``enrich_data`` (which also re-pulls the annual USGS/OWID/RMIS data),
so it can run daily to keep the per-commodity news feed current.
"""

from django.core.management.base import BaseCommand, CommandError

from commodities import services
from commodities.models import ImportRun


class Command(BaseCommand):
    help = "Rafraîchit les actualités de marché des matières (Google News, cron quotidien)."

    def handle(self, *args, **options):
        run = services.refresh_events()
        if run.status == ImportRun.Status.ERROR:
            raise CommandError(run.message)
        self.stdout.write(self.style.SUCCESS(run.message))
