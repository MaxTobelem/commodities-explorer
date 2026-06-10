"""Curated, source-attributed sector usages and everyday products.

There is no clean machine-readable source for "share by sector" / "everyday
products" (RMIS is graph/Excel + ECAS-gated and excludes gold), so this is a
hand-curated dataset from authoritative bodies (USGS, World Gold Council, Cobalt
Institute, EU Critical Raw Materials). It is the source of truth for usages /
compositions of the listed commodities (delete-then-insert), tagged
source="curated" and editable in the admin. Re-run to refresh from this file.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify

from commodities.models import (
    Commodity,
    CommodityUsage,
    Product,
    ProductComposition,
    Sector,
)

# slug -> {source, usages: [(sector, share%)], products: [(product, role)]}
CURATED = {
    "aluminium": {
        "source": "USGS / European Aluminium",
        "usages": [
            ("Transport", 35),
            ("Emballage", 22),
            ("Construction", 15),
            ("Électronique", 9),
            ("Machines & équipements", 8),
            ("Biens de consommation", 7),
        ],
        "products": [
            ("Canette de boisson", "Corps de la canette (aluminium recyclable)"),
            ("Avion", "Structure et fuselage (alliages légers)"),
            ("Voiture", "Carrosserie, jantes, blocs moteur"),
            ("Ordinateur portable", "Châssis / coque"),
            ("Câble électrique", "Conducteur (lignes haute tension)"),
        ],
    },
    "cobalt": {
        "source": "USGS / Cobalt Institute",
        "usages": [
            ("Batteries", 60),
            ("Superalliages", 15),
            ("Carbures & outils", 8),
            ("Catalyseurs", 6),
            ("Aimants", 4),
            ("Pigments", 3),
        ],
        "products": [
            ("Smartphone", "Cathode de la batterie lithium-ion"),
            ("Batterie de véhicule électrique", "Cathode (NMC / NCA)"),
            ("Ordinateur portable", "Batterie lithium-ion"),
            ("Turbine d'avion", "Superalliage résistant aux hautes températures"),
            ("Outil de coupe", "Liant des carbures (carbure de tungstène)"),
        ],
    },
    "or": {
        "source": "World Gold Council / USGS",
        "usages": [
            ("Bijouterie", 45),
            ("Investissement", 25),
            ("Banques centrales", 22),
            ("Électronique", 7),
        ],
        "products": [
            ("Smartphone", "Connecteurs et circuits (résistance à la corrosion)"),
            ("Bijou en or", "Matière principale"),
            ("Ordinateur portable", "Connecteurs dorés, circuits"),
            ("Carte à puce", "Contacts et microcircuits"),
        ],
    },
}


class Command(BaseCommand):
    help = "Importe le dataset curé (secteurs d'usage % + produits) depuis des sources autoritatives."

    @transaction.atomic
    def handle(self, *args, **options):
        usages = compositions = 0
        for slug, data in CURATED.items():
            commodity = Commodity.objects.filter(slug=slug).first()
            if commodity is None:
                continue

            # Curated set is authoritative for this commodity.
            CommodityUsage.objects.filter(commodity=commodity).delete()
            ProductComposition.objects.filter(commodity=commodity).delete()

            for sector_name, share in data["usages"]:
                sector, _ = Sector.objects.get_or_create(
                    slug=slugify(sector_name), defaults={"name": sector_name}
                )
                CommodityUsage.objects.create(
                    commodity=commodity,
                    sector=sector,
                    share_percent=Decimal(share),
                    description=f"Source : {data['source']}",
                    source="curated",
                    needs_review=False,
                )
                usages += 1

            for product_name, role in data["products"]:
                product, _ = Product.objects.get_or_create(
                    slug=slugify(product_name), defaults={"name": product_name}
                )
                ProductComposition.objects.create(
                    commodity=commodity,
                    product=product,
                    role=role,
                    source="curated",
                    needs_review=False,
                )
                compositions += 1

        self.stdout.write(
            self.style.SUCCESS(f"Dataset curé importé : {usages} usages, {compositions} compositions.")
        )
