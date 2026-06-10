"""Create/update the full commodity catalogue (energy, agriculture, fertilizers,
metals, precious + cobalt). Idempotent. Run `update_prices` / `backfill_prices`
afterwards to fetch their prices."""

from django.core.management.base import BaseCommand

from commodities.catalog import ensure_commodities


class Command(BaseCommand):
    help = "Crée/met à jour le catalogue complet des matières premières."

    def handle(self, *args, **options):
        n = ensure_commodities()
        self.stdout.write(self.style.SUCCESS(f"{n} matières dans le catalogue."))
