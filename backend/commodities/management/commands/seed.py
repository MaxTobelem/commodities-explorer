"""Seed an initial, illustrative dataset.

Idempotent: safe to re-run. Real figures are imported later by `update_prices`
and `enrich_data` (M2); this seed gives the dashboard something to show and the
tests a stable fixture. All rows are tagged source="seed".
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from commodities.models import (
    Commodity,
    CommodityProduction,
    CommodityReserve,
    CommodityUsage,
    Country,
    Event,
    EventImpact,
    Product,
    ProductComposition,
    Sector,
)

SOURCE = "seed"
YEAR = 2024

COUNTRIES = [
    ("Chine", "CN", "CHN", "Asie"),
    ("Australie", "AU", "AUS", "Océanie"),
    ("République démocratique du Congo", "CD", "COD", "Afrique"),
    ("Russie", "RU", "RUS", "Europe/Asie"),
    ("Guinée", "GN", "GIN", "Afrique"),
    ("Indonésie", "ID", "IDN", "Asie"),
    ("États-Unis", "US", "USA", "Amérique du Nord"),
    ("Canada", "CA", "CAN", "Amérique du Nord"),
    ("Afrique du Sud", "ZA", "ZAF", "Afrique"),
    ("Brésil", "BR", "BRA", "Amérique du Sud"),
    ("Inde", "IN", "IND", "Asie"),
    ("Pérou", "PE", "PER", "Amérique du Sud"),
]

COMMODITIES = [
    {
        "name": "Aluminium",
        "symbol": "ALU",
        "category": Commodity.Category.BASE,
        "price_unit": "USD/t",
        "price_provider": "worldbank",
        "price_symbol": "Aluminum",  # World Bank column label
        "description": "Métal léger très utilisé dans le transport, l'emballage et la construction.",
    },
    {
        "name": "Cobalt",
        "symbol": "LCO",
        "category": Commodity.Category.BATTERY,
        "price_unit": "USD/t",
        "price_provider": "usgs_price",  # cobalt absent du World Bank → prix annuel USGS
        "price_symbol": "Cobalt",
        "description": "Métal stratégique des batteries lithium-ion et des superalliages.",
    },
    {
        "name": "Or",
        "symbol": "XAU",
        "category": Commodity.Category.PRECIOUS,
        "price_unit": "USD/ozt",
        "price_provider": "worldbank",
        "price_symbol": "Gold",  # World Bank column label
        "description": "Métal précieux : valeur refuge, bijouterie et électronique.",
    },
]

SECTORS = [
    "Transport",
    "Construction",
    "Emballage",
    "Électronique",
    "Batteries",
    "Superalliages",
    "Bijouterie",
    "Investissement",
]

PRODUCTS = [
    "Smartphone",
    "Batterie de véhicule électrique",
    "Ordinateur portable",
    "Canette de boisson",
    "Bijou en or",
    "Avion",
]

EVENTS = [
    {
        "title": "Invasion de l'Ukraine (2022)",
        "type": Event.Type.WAR,
        "start_date": dt.date(2022, 2, 24),
        "description": "Conflit majeur ayant perturbé l'énergie et plusieurs marchés de métaux.",
    },
    {
        "title": "Tensions d'approvisionnement en RDC",
        "type": Event.Type.POLICY,
        "start_date": dt.date(2023, 1, 1),
        "description": "Instabilité autour de la production de cobalt en République démocratique du Congo.",
    },
    {
        "title": "Pandémie de COVID-19",
        "type": Event.Type.DISASTER,
        "start_date": dt.date(2020, 3, 1),
        "description": "Choc mondial sur la demande et les chaînes d'approvisionnement.",
    },
]

# commodity_symbol -> [(iso3, production_t, reserves_t)]
PRODUCTION_RESERVES = {
    "ALU": [
        ("CHN", 41000000, 0),
        ("IND", 4100000, 0),
        ("RUS", 3700000, 0),
        ("CAN", 3000000, 0),
        ("GIN", 0, 7400000000),  # bauxite reserves
        ("AUS", 1500000, 5300000000),
    ],
    "LCO": [
        ("COD", 130000, 6000000),
        ("IDN", 17000, 600000),
        ("AUS", 5900, 1500000),
        ("RUS", 8800, 250000),
        ("CAN", 3900, 220000),
    ],
    "XAU": [
        ("CHN", 370, 3000),
        ("AUS", 290, 12000),
        ("RUS", 310, 11100),
        ("USA", 170, 3000),
        ("PER", 100, 2300),
        ("ZAF", 100, 5000),
    ],
}

# commodity_symbol -> [(sector_name, share_percent)]
USAGES = {
    "ALU": [("Transport", 35), ("Construction", 25), ("Emballage", 20), ("Électronique", 10)],
    "LCO": [("Batteries", 70), ("Superalliages", 15), ("Électronique", 10)],
    "XAU": [("Bijouterie", 45), ("Investissement", 40), ("Électronique", 8)],
}

# commodity_symbol -> [(product_name, role)]
COMPOSITIONS = {
    "ALU": [("Canette de boisson", "Corps de la canette"), ("Avion", "Structure / fuselage"),
            ("Ordinateur portable", "Châssis")],
    "LCO": [("Smartphone", "Cathode de la batterie"),
            ("Batterie de véhicule électrique", "Cathode lithium-ion"),
            ("Ordinateur portable", "Batterie")],
    "XAU": [("Smartphone", "Connecteurs / circuits"), ("Bijou en or", "Matière principale"),
            ("Ordinateur portable", "Connecteurs")],
}

# event_title -> [(commodity_symbol, direction, magnitude)]
IMPACTS = {
    "Invasion de l'Ukraine (2022)": [
        ("ALU", EventImpact.Direction.UP, 30),
        ("XAU", EventImpact.Direction.UP, 12),
    ],
    "Tensions d'approvisionnement en RDC": [
        ("LCO", EventImpact.Direction.UP, 20),
    ],
    "Pandémie de COVID-19": [
        ("XAU", EventImpact.Direction.UP, 25),
        ("ALU", EventImpact.Direction.DOWN, 15),
    ],
}


class Command(BaseCommand):
    help = "Crée un jeu de données initial illustratif (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        countries = {}
        for name, iso2, iso3, region in COUNTRIES:
            obj, _ = Country.objects.update_or_create(
                iso3=iso3, defaults={"name": name, "iso2": iso2, "region": region}
            )
            countries[iso3] = obj

        commodities = {}
        for data in COMMODITIES:
            obj, _ = Commodity.objects.update_or_create(
                slug=slugify(data["name"]),
                defaults={
                    "name": data["name"],
                    "symbol": data["symbol"],
                    "category": data["category"],
                    "price_unit": data["price_unit"],
                    "price_provider": data["price_provider"],
                    "price_symbol": data["price_symbol"],
                    "description": data["description"],
                    "is_active": True,
                },
            )
            commodities[data["symbol"]] = obj

        sectors = {}
        for name in SECTORS:
            obj, _ = Sector.objects.update_or_create(slug=slugify(name), defaults={"name": name})
            sectors[name] = obj

        products = {}
        for name in PRODUCTS:
            obj, _ = Product.objects.update_or_create(slug=slugify(name), defaults={"name": name})
            products[name] = obj

        events = {}
        for data in EVENTS:
            obj, _ = Event.objects.update_or_create(
                slug=slugify(data["title"]),
                defaults={
                    "title": data["title"],
                    "type": data["type"],
                    "start_date": data["start_date"],
                    "description": data["description"],
                },
            )
            events[data["title"]] = obj

        for symbol, rows in PRODUCTION_RESERVES.items():
            commodity = commodities[symbol]
            for iso3, production_t, reserves_t in rows:
                country = countries[iso3]
                if production_t:
                    CommodityProduction.objects.update_or_create(
                        commodity=commodity, country=country, year=YEAR,
                        defaults={"production_t": Decimal(production_t), "source": SOURCE},
                    )
                if reserves_t:
                    CommodityReserve.objects.update_or_create(
                        commodity=commodity, country=country, year=YEAR,
                        defaults={"reserves_t": Decimal(reserves_t), "source": SOURCE},
                    )

        for symbol, rows in USAGES.items():
            commodity = commodities[symbol]
            for sector_name, share in rows:
                CommodityUsage.objects.update_or_create(
                    commodity=commodity, sector=sectors[sector_name],
                    defaults={"share_percent": Decimal(share), "source": SOURCE, "needs_review": False},
                )

        for symbol, rows in COMPOSITIONS.items():
            commodity = commodities[symbol]
            for product_name, role in rows:
                ProductComposition.objects.update_or_create(
                    commodity=commodity, product=products[product_name],
                    defaults={"role": role, "source": SOURCE, "needs_review": False},
                )

        for event_title, rows in IMPACTS.items():
            event = events[event_title]
            for symbol, direction, magnitude in rows:
                EventImpact.objects.update_or_create(
                    event=event, commodity=commodities[symbol],
                    defaults={
                        "direction": direction,
                        "magnitude": Decimal(magnitude),
                        "source": SOURCE,
                        "needs_review": False,
                    },
                )

        self.stdout.write(
            self.style.SUCCESS(
                f"Seed OK — {Commodity.objects.count()} matières, "
                f"{Country.objects.count()} pays, {Sector.objects.count()} secteurs, "
                f"{Product.objects.count()} produits, {Event.objects.count()} événements."
            )
        )
