"""Authoritative commodity catalogue.

(name, symbol, category, price_unit, price_provider, price_symbol). Prices come
from the World Bank Pink Sheet (price_symbol = WB column label), except cobalt
(USGS annual). Re-run `import_commodities` to apply changes.
"""

from __future__ import annotations

from django.db import transaction
from django.utils.text import slugify

from commodities.models import Commodity

_E = Commodity.Category.ENERGY
_A = Commodity.Category.AGRICULTURAL
_F = Commodity.Category.FERTILIZER
_B = Commodity.Category.BASE
_P = Commodity.Category.PRECIOUS
_BAT = Commodity.Category.BATTERY

COMMODITY_CATALOG = [
    # Énergie
    ("Pétrole brut (Brent)", "BRENT", _E, "USD/bbl", "worldbank", "Crude oil, Brent"),
    ("Gaz naturel (Europe)", "GAZ-EU", _E, "USD/mmbtu", "worldbank", "Natural gas, Europe"),
    ("Gaz naturel (US)", "GAZ-US", _E, "USD/mmbtu", "worldbank", "Natural gas, US"),
    ("GNL (Japon)", "GNL", _E, "USD/mmbtu", "worldbank", "Liquefied natural gas, Japan"),
    ("Charbon (Australie)", "CHARBON", _E, "USD/t", "worldbank", "Coal, Australian"),
    # Agricole — boissons
    ("Cacao", "CACAO", _A, "USD/kg", "worldbank", "Cocoa"),
    ("Café (Arabica)", "CAFE", _A, "USD/kg", "worldbank", "Coffee, Arabica"),
    ("Thé", "THE", _A, "USD/kg", "worldbank", "Tea, avg 3 auctions"),
    # Agricole — oléagineux
    ("Huile de palme", "PALME", _A, "USD/t", "worldbank", "Palm oil"),
    ("Soja", "SOJA", _A, "USD/t", "worldbank", "Soybeans"),
    ("Huile de soja", "H-SOJA", _A, "USD/t", "worldbank", "Soybean oil"),
    ("Huile de tournesol", "TOURNESOL", _A, "USD/t", "worldbank", "Sunflower oil"),
    # Agricole — céréales
    ("Blé (US HRW)", "BLE", _A, "USD/t", "worldbank", "Wheat, US HRW"),
    ("Maïs", "MAIS", _A, "USD/t", "worldbank", "Maize"),
    ("Riz (Thaï 5%)", "RIZ", _A, "USD/t", "worldbank", "Rice, Thai 5%"),
    ("Orge", "ORGE", _A, "USD/t", "worldbank", "Barley"),
    # Agricole — autres aliments
    ("Sucre (mondial)", "SUCRE", _A, "USD/kg", "worldbank", "Sugar, world"),
    ("Banane", "BANANE", _A, "USD/kg", "worldbank", "Banana, US"),
    ("Bœuf", "BOEUF", _A, "USD/kg", "worldbank", "Beef"),
    ("Crevettes", "CREVETTE", _A, "USD/kg", "worldbank", "Shrimps, Mexican"),
    # Agricole — matières premières
    ("Coton", "COTON", _A, "USD/kg", "worldbank", "Cotton, A Index"),
    ("Caoutchouc", "CAOUT", _A, "USD/kg", "worldbank", "Rubber, TSR20"),
    ("Bois (grumes)", "BOIS", _A, "USD/m3", "worldbank", "Logs, Malaysian"),
    ("Tabac", "TABAC", _A, "USD/t", "worldbank", "Tobacco, US import u.v."),
    # Engrais
    ("Phosphate (roche)", "PHOS", _F, "USD/t", "worldbank", "Phosphate rock"),
    ("DAP (engrais)", "DAP", _F, "USD/t", "worldbank", "DAP"),
    ("Urée", "UREE", _F, "USD/t", "worldbank", "Urea"),
    ("Chlorure de potassium", "POTASSE", _F, "USD/t", "worldbank", "Potassium chloride"),
    # Métaux de base
    ("Aluminium", "ALU", _B, "USD/t", "worldbank", "Aluminum"),
    ("Cuivre", "CUIVRE", _B, "USD/t", "worldbank", "Copper"),
    ("Minerai de fer", "FER", _B, "USD/dmtu", "worldbank", "Iron ore, cfr spot"),
    ("Plomb", "PLOMB", _B, "USD/t", "worldbank", "Lead"),
    ("Étain", "ETAIN", _B, "USD/t", "worldbank", "Tin"),
    ("Nickel", "NICKEL", _B, "USD/t", "worldbank", "Nickel"),
    ("Zinc", "ZINC", _B, "USD/t", "worldbank", "Zinc"),
    # Métaux précieux
    ("Or", "XAU", _P, "USD/ozt", "worldbank", "Gold"),
    ("Platine", "PLATINE", _P, "USD/ozt", "worldbank", "Platinum"),
    ("Argent", "ARGENT", _P, "USD/ozt", "worldbank", "Silver"),
    # Batteries — cobalt (prix annuel USGS, absent du World Bank)
    ("Cobalt", "LCO", _BAT, "USD/t", "usgs_price", "Cobalt"),
]


@transaction.atomic
def ensure_commodities() -> int:
    """Idempotently create/update every catalogue commodity (keyed by slug)."""
    for name, symbol, category, unit, provider, price_symbol in COMMODITY_CATALOG:
        Commodity.objects.update_or_create(
            slug=slugify(name),
            defaults={
                "name": name,
                "symbol": symbol,
                "category": category,
                "price_unit": unit,
                "price_provider": provider,
                "price_symbol": price_symbol,
                "is_active": True,
            },
        )
    return len(COMMODITY_CATALOG)
