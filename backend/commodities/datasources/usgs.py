"""USGS provider — real world production & reserves (Mineral Commodity Summaries).

Source: USGS MCS Data Release (public domain). The consolidated *World Data* CSV
holds production (2023 + 2024-estimate) and reserves (2024) by country for ~77
commodities, with a `TYPE` column (mine/smelter/refinery/capacity…) and a
`UNIT_MEAS` column (metric tons / thousand metric tons / kilograms…).

The CSV lives in a ZIP attached to a ScienceBase item; we resolve the file from
the item JSON, so the only thing to bump for a new year is ``USGS_MCS_ITEM_ID``.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import pycountry
import requests
from django.conf import settings

from .base import EnrichmentProvider, EnrichmentResult, ProductionRecord, ReserveRecord

if TYPE_CHECKING:
    from commodities.models import Commodity

SCIENCEBASE_ITEM = "https://www.sciencebase.gov/catalog/item/{item_id}?format=json"
USER_AGENT = "Mozilla/5.0 (commodities-explorer research dashboard)"

# Our commodity slug → USGS COMMODITY label (extend via USGS_COMMODITY_NAMES).
DEFAULT_USGS_NAMES = {
    "aluminium": "Aluminum",
    "cobalt": "Cobalt",
    "or": "Gold",
    "cuivre": "Copper",
    "nickel": "Nickel",
    "zinc": "Zinc",
    "plomb": "Lead",
    "etain": "Tin",
    "argent": "Silver",
    "minerai-de-fer": "Iron Ore",
    "platine": "Platinum-Group metals",
    "magnesium": "Magnesium metal",  # USGS splits "Magnesium metal" / "Magnesium compounds"
}

# USGS country spellings → (ISO3, display name); pycountry resolves the rest.
COUNTRY_OVERRIDES: dict[str, tuple[str, str]] = {
    "congo (kinshasa)": ("COD", "RD Congo"),
    "congo (brazzaville)": ("COG", "Congo"),
    "korea, republic of": ("KOR", "Corée du Sud"),
    "korea, north": ("PRK", "Corée du Nord"),
    "burma": ("MMR", "Birmanie"),
    "turkey": ("TUR", "Turquie"),
    "russia": ("RUS", "Russie"),
    "bolivia": ("BOL", "Bolivie"),
    "iran": ("IRN", "Iran"),
    "tanzania": ("TZA", "Tanzanie"),
    "venezuela": ("VEN", "Venezuela"),
    "vietnam": ("VNM", "Vietnam"),
    "laos": ("LAO", "Laos"),
    "cote d'ivoire": ("CIV", "Côte d'Ivoire"),
    "côte d'ivoire": ("CIV", "Côte d'Ivoire"),
    "the bahamas": ("BHS", "Bahamas"),
    "united states": ("USA", "États-Unis"),
}
# Rows whose COUNTRY contains one of these are aggregates, not a single country.
SKIP_TOKENS = ("world", "other countr", "total", " and ", "european", "unspecified")

# USGS reports several production stages; we keep ONE primary stage per commodity
# (preferring raw extraction) so a metal's producers stay comparable, then label it.
STAGE_PRIORITY = ("mine", "smelter", "refinery")
STAGE_LABELS = {
    "mine": "Production minière",
    "smelter": "Production de fonderie",
    "refinery": "Production de raffinage",
}


class UsgsProvider(EnrichmentProvider):
    key = "usgs"

    @property
    def enabled(self) -> bool:
        return getattr(settings, "USGS_ENABLED", True)

    @property
    def item_id(self) -> str:
        return getattr(settings, "USGS_MCS_ITEM_ID", "677eaf95d34e760b392c4970")  # MCS 2025

    @property
    def timeout(self) -> int:
        return getattr(settings, "USGS_TIMEOUT", 60)

    @property
    def commodity_names(self) -> dict[str, str]:
        return {**DEFAULT_USGS_NAMES, **getattr(settings, "USGS_COMMODITY_NAMES", {})}

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        if not self.enabled:
            return EnrichmentResult()
        names = self.commodity_names
        wanted = {
            (names.get(c.slug) or names.get(c.price_symbol) or c.name): c for c in commodities
        }
        if not wanted:
            return EnrichmentResult()
        csv_text = self._download_world_csv()
        if not csv_text:
            return EnrichmentResult()
        return self.parse_world_data(csv_text, wanted)

    # -- internals -----------------------------------------------------------

    def _download_world_csv(self) -> str | None:
        headers = {"User-Agent": USER_AGENT}
        item = requests.get(
            SCIENCEBASE_ITEM.format(item_id=self.item_id), headers=headers, timeout=self.timeout
        )
        item.raise_for_status()
        files = item.json().get("files", []) or []
        url = next(
            (f["downloadUri"] for f in files if str(f.get("name", "")).startswith("World_Data")),
            None,
        )
        if not url:
            return None
        archive = requests.get(url, headers=headers, timeout=self.timeout)
        archive.raise_for_status()
        with zipfile.ZipFile(io.BytesIO(archive.content)) as zf:
            csv_name = next((n for n in zf.namelist() if n.lower().endswith(".csv")), None)
            if not csv_name:
                return None
            return zf.read(csv_name).decode("utf-8-sig")

    @classmethod
    def parse_world_data(
        cls, csv_text: str, wanted: dict[str, Commodity]
    ) -> EnrichmentResult:
        result = EnrichmentResult()
        # Group production rows per commodity so we can keep ONE primary stage
        # (mine > smelter > refinery) — otherwise e.g. copper mixes mine and
        # refinery figures across countries and rankings become inconsistent.
        rows_by_commodity: dict[Commodity, list[tuple[dict, str]]] = defaultdict(list)
        for row in csv.DictReader(io.StringIO(csv_text)):
            commodity = wanted.get((row.get("COMMODITY") or "").strip())
            if commodity is None or "production" not in (row.get("TYPE") or "").lower():
                continue
            rows_by_commodity[commodity].append((row, cls._stage(row.get("TYPE") or "")))

        for commodity, entries in rows_by_commodity.items():
            stages = {stage for _, stage in entries}
            primary = next((s for s in STAGE_PRIORITY if s in stages), "")
            note = STAGE_LABELS.get(primary, "Production")
            for row, stage in entries:
                if primary and stage != primary:
                    continue  # drop secondary stages for a consistent metric
                iso3, name = cls._resolve_country(row.get("COUNTRY") or "")
                if iso3 is None:
                    continue
                unit = (row.get("UNIT_MEAS") or "").strip().lower()

                production = cls._to_tonnes(row.get("PROD_EST_ 2024"), unit)
                year = 2024
                if production is None:
                    production = cls._to_tonnes(row.get("PROD_2023"), unit)
                    year = 2023
                if production is not None:
                    result.production.append(
                        ProductionRecord(
                            commodity, iso3, name, year, production, "usgs", note=note
                        )
                    )

                reserves = cls._to_tonnes(row.get("RESERVES_2024"), unit)
                if reserves is not None:
                    result.reserves.append(
                        ReserveRecord(commodity, iso3, name, 2024, reserves, "usgs")
                    )
        return result

    @staticmethod
    def _stage(type_str: str) -> str:
        """Map a USGS TYPE label to a coarse production stage (mine/smelter/...)."""
        lowered = type_str.lower()
        return next((s for s in STAGE_PRIORITY if s in lowered), "")

    @staticmethod
    def _to_tonnes(raw: str | None, unit: str) -> Decimal | None:
        if raw is None:
            return None
        text = str(raw).replace(",", "").strip()
        if not text or text in {"—", "NA", "W", "XX"}:
            return None
        try:
            value = Decimal(text)
        except InvalidOperation:
            return None
        if "thousand" in unit:
            factor = Decimal(1000)
        elif "million" in unit:
            factor = Decimal(1_000_000)
        elif "kilogram" in unit:
            factor = Decimal("0.001")
        else:
            factor = Decimal(1)
        return (value * factor).quantize(Decimal("0.01"))

    @staticmethod
    def _resolve_country(raw: str) -> tuple[str | None, str]:
        key = raw.strip().lower()
        if not key or any(token in key for token in SKIP_TOKENS):
            return None, raw
        if key in COUNTRY_OVERRIDES:
            return COUNTRY_OVERRIDES[key]
        try:
            country = pycountry.countries.lookup(raw.strip())
        except LookupError:
            try:
                matches = pycountry.countries.search_fuzzy(raw.strip())
            except LookupError:
                return None, raw
            country = matches[0] if matches else None
        if country is None:
            return None, raw
        return country.alpha_3, getattr(country, "common_name", country.name)
