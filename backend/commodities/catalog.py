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

# (nom, symbole, catégorie, unité, fournisseur historique/repli, label WB, ticker Commodities-API)
# La 7ᵉ colonne (api_symbol) alimente la MAJ QUOTIDIENNE via Commodities-API ; un
# ticker absent/erroné se replie proprement sur le mensuel World Bank. Vérifier /
# compléter les tickers avec `manage.py check_api_symbols`. Vide ⇒ mensuel uniquement.
COMMODITY_CATALOG = [
    # Énergie
    ("Pétrole brut (Brent)", "BRENT", _E, "USD/bbl", "worldbank", "Crude oil, Brent", "BRENTOIL"),
    ("Gaz naturel (Europe)", "GAZ-EU", _E, "USD/mmbtu", "worldbank", "Natural gas, Europe", ""),
    ("Gaz naturel (US)", "GAZ-US", _E, "USD/mmbtu", "worldbank", "Natural gas, US", "NG"),
    ("GNL (Japon)", "GNL", _E, "USD/mmbtu", "worldbank", "Liquefied natural gas, Japan", "LNG-J"),
    ("Charbon (Australie)", "CHARBON", _E, "USD/t", "worldbank", "Coal, Australian", "COAL"),
    # Agricole — boissons
    ("Cacao", "CACAO", _A, "USD/kg", "worldbank", "Cocoa", "COCOA"),
    ("Café (Arabica)", "CAFE", _A, "USD/kg", "worldbank", "Coffee, Arabica", "COFFEE"),
    ("Thé", "THE", _A, "USD/kg", "worldbank", "Tea, avg 3 auctions", ""),
    # Agricole — oléagineux
    ("Huile de palme", "PALME", _A, "USD/t", "worldbank", "Palm oil", "CPO"),
    ("Soja", "SOJA", _A, "USD/t", "worldbank", "Soybeans", "SOYBEAN"),
    ("Huile de soja", "H-SOJA", _A, "USD/t", "worldbank", "Soybean oil", "ZL"),
    ("Huile de tournesol", "TOURNESOL", _A, "USD/t", "worldbank", "Sunflower oil", ""),
    # Agricole — céréales
    ("Blé (US HRW)", "BLE", _A, "USD/t", "worldbank", "Wheat, US HRW", "WHEAT"),
    ("Maïs", "MAIS", _A, "USD/t", "worldbank", "Maize", "CORN"),
    ("Riz", "RIZ", _A, "USD/t", "worldbank", "", "RICE"),  # rough rice US (CA daily) ; WB Thaï retiré
    ("Orge", "ORGE", _A, "USD/t", "worldbank", "Barley", ""),
    # Agricole — autres aliments
    ("Sucre (mondial)", "SUCRE", _A, "USD/kg", "worldbank", "Sugar, world", "SUGAR"),
    ("Banane", "BANANE", _A, "USD/kg", "worldbank", "Banana, US", "BANA-US"),
    ("Bœuf", "BOEUF", _A, "USD/kg", "worldbank", "Beef", ""),
    ("Crevettes", "CREVETTE", _A, "USD/kg", "worldbank", "Shrimps, Mexican", ""),
    # Agricole — matières premières
    ("Coton", "COTON", _A, "USD/kg", "worldbank", "Cotton, A Index", "COTTON"),
    ("Caoutchouc", "CAOUT", _A, "USD/kg", "worldbank", "Rubber, TSR20", ""),
    ("Bois (grumes)", "BOIS", _A, "USD/m3", "worldbank", "Logs, Malaysian", ""),
    ("Tabac", "TABAC", _A, "USD/t", "worldbank", "Tobacco, US import u.v.", ""),
    # Engrais
    ("Phosphate (roche)", "PHOS", _F, "USD/t", "worldbank", "Phosphate rock", ""),
    ("DAP (engrais)", "DAP", _F, "USD/t", "worldbank", "DAP", ""),
    ("Urée", "UREE", _F, "USD/t", "worldbank", "Urea", "UREA"),
    ("Chlorure de potassium", "POTASSE", _F, "USD/t", "worldbank", "Potassium chloride", ""),
    # Métaux de base
    ("Aluminium", "ALU", _B, "USD/t", "worldbank", "Aluminum", "ALU"),
    ("Cuivre", "CUIVRE", _B, "USD/t", "worldbank", "Copper", "XCU"),
    ("Minerai de fer", "FER", _B, "USD/dmtu", "worldbank", "Iron ore, cfr spot", "IRON"),
    ("Plomb", "PLOMB", _B, "USD/t", "worldbank", "Lead", "LEAD"),
    ("Étain", "ETAIN", _B, "USD/t", "worldbank", "Tin", "TIN"),
    ("Nickel", "NICKEL", _B, "USD/t", "worldbank", "Nickel", "NI"),
    ("Zinc", "ZINC", _B, "USD/t", "worldbank", "Zinc", "LME-ZNC"),
    # Métaux précieux
    ("Or", "XAU", _P, "USD/ozt", "worldbank", "Gold", "XAU"),
    ("Platine", "PLATINE", _P, "USD/ozt", "worldbank", "Platinum", "XPT"),
    ("Argent", "ARGENT", _P, "USD/ozt", "worldbank", "Silver", "XAG"),
    # Batteries — cobalt (prix historique annuel USGS, absent du World Bank)
    ("Cobalt", "LCO", _BAT, "USD/t", "usgs_price", "Cobalt", "LCO"),
]


@transaction.atomic
def ensure_commodities() -> int:
    """Idempotently create/update every catalogue commodity (keyed by slug)."""
    for name, symbol, category, unit, provider, price_symbol, api_symbol in COMMODITY_CATALOG:
        Commodity.objects.update_or_create(
            slug=slugify(name),
            defaults={
                "name": name,
                "symbol": symbol,
                "category": category,
                "price_unit": unit,
                "price_provider": provider,
                "price_symbol": price_symbol,
                "api_symbol": api_symbol,
                "is_active": True,
            },
        )
    return len(COMMODITY_CATALOG)
