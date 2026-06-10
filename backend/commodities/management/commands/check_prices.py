"""Validate the Commodities-API key and preview parsed prices WITHOUT saving.

Run this after setting COMMODITIES_API_KEY to confirm the key works and to check
that each commodity's `price_unit` matches what the API returns:

    uv run python manage.py check_prices
"""

from django.core.management.base import BaseCommand, CommandError

from commodities.datasources.registry import get_price_provider
from commodities.models import Commodity


class Command(BaseCommand):
    help = "Valide la clé Commodities-API et affiche les cours parsés (sans enregistrer)."

    def handle(self, *args, **options):
        commodities = list(
            Commodity.objects.filter(is_active=True, price_provider="commodities_api")
        )
        if not commodities:
            self.stdout.write(self.style.WARNING("Aucune matière active sur 'commodities_api'."))
            return

        provider = get_price_provider("commodities_api")
        if provider is None:  # pragma: no cover - registry misconfig
            raise CommandError("Fournisseur 'commodities_api' introuvable dans le registry.")

        try:
            results = provider.fetch_latest(commodities)
        except Exception as exc:  # noqa: BLE001 — surface the failure clearly to the operator
            raise CommandError(f"Échec de l'appel Commodities-API : {exc}") from exc

        priced = {r.commodity_id if hasattr(r, "commodity_id") else r.commodity.pk for r in results}
        for r in results:
            self.stdout.write(
                f"  {r.commodity.name:<14} {r.commodity.price_symbol:<6} "
                f"{r.price_usd} USD / {r.price_eur} EUR   "
                f"(unité configurée : {r.commodity.price_unit}) @ {r.date}"
            )
        missing = [c.name for c in commodities if c.pk not in priced]
        if missing:
            self.stdout.write(
                self.style.WARNING(f"Non couverts par l'API : {', '.join(missing)}")
            )
        self.stdout.write(
            self.style.SUCCESS(f"{len(results)} cours récupérés — clé valide. (Rien enregistré.)")
        )
