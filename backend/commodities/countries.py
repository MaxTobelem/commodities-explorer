"""Canonical French country names, keyed by ISO 3166-1 alpha-3.

Single source of truth so every data source (USGS, OWID, seed) stores the same
French label for a country. Backed by CLDR data via Babel (no hand-maintained
list); a few overrides cover spellings we prefer over the CLDR default.
"""

from __future__ import annotations

import functools

import pycountry
from babel import Locale

# Preferred French names where we want a specific form (e.g. the full RDC name).
_OVERRIDES: dict[str, str] = {
    "COD": "République démocratique du Congo",
    "COG": "Congo-Brazzaville",
    "USA": "États-Unis",
    "GBR": "Royaume-Uni",
    "KOR": "Corée du Sud",
    "PRK": "Corée du Nord",
}


@functools.lru_cache(maxsize=1)
def _territories() -> dict[str, str]:
    return Locale("fr").territories


@functools.lru_cache(maxsize=1024)
def french_name(iso3: str, fallback: str = "") -> str:
    """Return the canonical French name for an ISO3 code (or ``fallback``)."""
    iso3 = (iso3 or "").upper()
    if iso3 in _OVERRIDES:
        return _OVERRIDES[iso3]
    country = pycountry.countries.get(alpha_3=iso3)
    if country is not None:
        name = _territories().get(country.alpha_2)
        if name:
            return name
    return fallback or iso3


@functools.lru_cache(maxsize=1)
def _en_territories() -> dict[str, str]:
    return Locale("en").territories


# Search-friendly English names where the CLDR default is awkward for news search.
_EN_OVERRIDES: dict[str, str] = {
    "COD": "Democratic Republic of the Congo",
    "USA": "United States",
    "GBR": "United Kingdom",
    "KOR": "South Korea",
    "PRK": "North Korea",
    "RUS": "Russia",
    "IRN": "Iran",
    "BOL": "Bolivia",
    "VEN": "Venezuela",
    "LAO": "Laos",
    "SYR": "Syria",
    "TZA": "Tanzania",
}


@functools.lru_cache(maxsize=1024)
def english_name(iso3: str, fallback: str = "") -> str:
    """Return a search-friendly English name for an ISO3 code (or ``fallback``)."""
    iso3 = (iso3 or "").upper()
    if iso3 in _EN_OVERRIDES:
        return _EN_OVERRIDES[iso3]
    country = pycountry.countries.get(alpha_3=iso3)
    if country is not None:
        name = _en_territories().get(country.alpha_2)
        if name:
            return name
    return fallback or iso3
