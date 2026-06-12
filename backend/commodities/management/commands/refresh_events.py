"""Refresh only the GDELT events/impacts (for a frequent cron).

    python manage.py refresh_events

Lighter than ``enrich_data`` (which also re-pulls the annual USGS/OWID/RMIS data),
so it can run on a frequent schedule to keep the events timeline current.
"""

from django.core.management.base import BaseCommand, CommandError

from commodities import services
from commodities.models import ImportRun


class Command(BaseCommand):
    help = "Rafraîchit uniquement les événements GDELT (cron fréquent)."

    def handle(self, *args, **options):
        run = services.refresh_events()
        if run.status == ImportRun.Status.ERROR:
            raise CommandError(run.message)
        self.stdout.write(self.style.SUCCESS(run.message))
