"""Validate each active commodity's Commodities-API ticker (`api_symbol`).

Calls the live Commodities-API ``/symbols`` endpoint (needs COMMODITIES_API_KEY)
and reports, per commodity, whether its daily-price ticker is supported, plus
supported tickers not yet mapped — so daily coverage can be completed in admin.
"""

from __future__ import annotations

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from commodities.models import Commodity

# Meta keys that may sit alongside the symbol→name pairs in some response shapes.
_META_KEYS = {"success", "error", "data", "rates", "date", "timestamp", "base", "unit"}


def _symbol_map(payload: object) -> dict:
    """Extract the {symbol: name} mapping across Commodities-API response shapes.

    The live ``/symbols`` endpoint returns the map at the JSON **root**
    (``{"ALU": "Aluminum", ...}``); older/wrapped shapes nest it under
    ``"symbols"`` or ``"data"."symbols"``.
    """
    if not isinstance(payload, dict):
        return {}
    if isinstance(payload.get("symbols"), dict):
        return payload["symbols"]
    data = payload.get("data")
    if isinstance(data, dict) and isinstance(data.get("symbols"), dict):
        return data["symbols"]
    return {k: v for k, v in payload.items() if k not in _META_KEYS and isinstance(v, str)}


class Command(BaseCommand):
    help = "Vérifie les tickers Commodities-API (api_symbol) des matières actives."

    def handle(self, *args, **options) -> None:
        key = getattr(settings, "COMMODITIES_API_KEY", "")
        if not key:
            raise CommandError(
                "COMMODITIES_API_KEY manquant — configurez la clé dans l'environnement."
            )
        base = getattr(
            settings, "COMMODITIES_API_BASE_URL", "https://api.commodities-api.com/api"
        ).rstrip("/")
        response = requests.get(f"{base}/symbols", params={"access_key": key}, timeout=20)
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict) and payload.get("success") is False:
            raise CommandError(f"Commodities-API erreur: {payload.get('error')}")
        supported = {str(s).upper(): name for s, name in _symbol_map(payload).items()}

        ok: list[tuple[str, str]] = []
        bad: list[tuple[str, str]] = []
        blank: list[str] = []
        mapped: set[str] = set()
        for commodity in Commodity.objects.filter(is_active=True).order_by("name"):
            sym = (commodity.api_symbol or "").upper()
            if not sym:
                blank.append(commodity.name)
            elif sym in supported:
                ok.append((commodity.name, sym))
                mapped.add(sym)
            else:
                bad.append((commodity.name, sym))

        self.stdout.write(
            self.style.MIGRATE_HEADING(f"{len(supported)} tickers supportés par Commodities-API")
        )
        self.stdout.write(self.style.SUCCESS(f"✓ {len(ok)} matières mappées (cours quotidien) :"))
        for name, sym in ok:
            self.stdout.write(f"    {name}: {sym} ({supported[sym]})")
        if bad:
            self.stdout.write(
                self.style.ERROR(f"✗ {len(bad)} tickers INVALIDES (repli mensuel World Bank) :")
            )
            for name, sym in bad:
                self.stdout.write(f"    {name}: {sym} — introuvable")
        if blank:
            self.stdout.write(
                self.style.WARNING(f"– {len(blank)} matières sans ticker (mensuel uniquement) :")
            )
            for name in blank:
                self.stdout.write(f"    {name}")
        unused = sorted(set(supported) - mapped)
        if unused:
            self.stdout.write(
                self.style.MIGRATE_HEADING(
                    f"{len(unused)} tickers supportés non utilisés (à compléter en admin) :"
                )
            )
            for sym in unused:
                self.stdout.write(f"    {sym}: {supported[sym]}")
