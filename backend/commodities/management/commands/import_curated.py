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
# Parts sourcées (sommant à ~100 %) auprès d'organismes de référence ; les noms de
# secteurs sont réutilisés entre matières pour alimenter le filtrage croisé.
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
    "cuivre": {
        "source": "USGS / ICSG",
        "usages": [
            ("Construction", 28),
            ("Électronique", 23),
            ("Machines & équipements", 20),
            ("Réseaux & infrastructures", 16),
            ("Transport", 13),
        ],
        "products": [
            ("Câble électrique", "Conducteur (excellente conductivité)"),
            ("Smartphone", "Circuits imprimés et connecteurs"),
            ("Plomberie", "Tuyaux et raccords"),
            ("Voiture", "Faisceaux électriques, moteur"),
            ("Moteur électrique", "Bobinages"),
        ],
    },
    "nickel": {
        "source": "USGS / Nickel Institute",
        "usages": [
            ("Acier inoxydable", 65),
            ("Batteries", 12),
            ("Alliages non ferreux", 8),
            ("Placage", 7),
            ("Fonderie", 5),
            ("Autres", 3),
        ],
        "products": [
            ("Couverts en inox", "Acier inoxydable"),
            ("Batterie de véhicule électrique", "Cathode (NMC)"),
            ("Turbine d'avion", "Superalliage"),
            ("Évier de cuisine", "Acier inoxydable"),
            ("Pièce de monnaie", "Alliage cupronickel"),
        ],
    },
    "zinc": {
        "source": "USGS / IZA",
        "usages": [
            ("Galvanisation", 60),
            ("Alliages & laiton", 15),
            ("Moulage (Zamak)", 14),
            ("Chimie & oxydes", 8),
            ("Semi-produits", 3),
        ],
        "products": [
            ("Glissière de sécurité", "Acier galvanisé anticorrosion"),
            ("Toiture", "Zinc de couverture"),
            ("Pile", "Anode en zinc"),
            ("Crème solaire", "Oxyde de zinc (filtre UV)"),
            ("Robinet", "Laiton (alliage cuivre-zinc)"),
        ],
    },
    "plomb": {
        "source": "USGS / ILA",
        "usages": [
            ("Batteries", 85),
            ("Munitions & gaines", 6),
            ("Pigments & composés", 4),
            ("Alliages", 3),
            ("Laminés & extrudés", 2),
        ],
        "products": [
            ("Batterie de voiture", "Batterie plomb-acide (démarrage)"),
            ("Protection radiologique", "Tablier anti rayons X"),
            ("Câble sous-marin", "Gaine d'étanchéité"),
            ("Munition", "Cœur de projectile"),
            ("Vitrail", "Résille de plomb"),
        ],
    },
    "etain": {
        "source": "USGS / International Tin Association",
        "usages": [
            ("Soudure électronique", 48),
            ("Produits chimiques", 18),
            ("Fer-blanc & étamage", 12),
            ("Batteries", 9),
            ("Bronze & laiton", 7),
            ("Verre", 6),
        ],
        "products": [
            ("Carte électronique", "Soudure des composants"),
            ("Boîte de conserve", "Fer-blanc étamé"),
            ("Smartphone", "Soudures internes"),
            ("Écran plat", "Verre (procédé float)"),
            ("Roulement", "Bronze (alliage)"),
        ],
    },
    "argent": {
        "source": "The Silver Institute",
        "usages": [
            ("Électronique", 40),
            ("Bijouterie", 18),
            ("Investissement", 17),
            ("Photovoltaïque", 14),
            ("Argenterie", 6),
            ("Photographie", 5),
        ],
        "products": [
            ("Panneau solaire", "Pâte conductrice des cellules"),
            ("Smartphone", "Contacts et circuits"),
            ("Bijou en argent", "Matière principale"),
            ("Couverts en argent", "Argenterie"),
            ("Miroir", "Couche réfléchissante"),
        ],
    },
    "platine": {
        "source": "USGS / WPIC",
        "usages": [
            ("Pots catalytiques", 40),
            ("Bijouterie", 25),
            ("Industrie chimique & verre", 15),
            ("Investissement", 10),
            ("Électronique", 5),
            ("Médical", 5),
        ],
        "products": [
            ("Pot catalytique", "Catalyseur de dépollution"),
            ("Bijou en platine", "Matière principale"),
            ("Verre LCD", "Cuves de fusion"),
            ("Stimulateur cardiaque", "Électrodes biocompatibles"),
            ("Capteur à oxygène", "Électrode"),
        ],
    },
    "minerai-de-fer": {
        "source": "USGS / World Steel",
        "usages": [
            ("Sidérurgie", 98),
            ("Ferro-alliages", 1),
            ("Autres (ciment, médias)", 1),
        ],
        "products": [
            ("Voiture", "Acier de carrosserie"),
            ("Bâtiment", "Poutres et armatures"),
            ("Électroménager", "Tôle d'acier"),
            ("Rail de chemin de fer", "Acier"),
            ("Outil", "Acier"),
        ],
    },
    "petrole-brut-brent": {
        "source": "AIE / EIA",
        "usages": [
            ("Transport", 55),
            ("Pétrochimie & plastiques", 14),
            ("Industrie", 12),
            ("Chauffage & bâtiment", 10),
            ("Production électrique", 5),
            ("Bitume & lubrifiants", 4),
        ],
        "products": [
            ("Carburant", "Essence, diesel, kérosène"),
            ("Plastique", "Matière première pétrochimique"),
            ("Route", "Bitume / asphalte"),
            ("Vêtement synthétique", "Polyester, nylon"),
            ("Médicament", "Synthèse et excipients"),
        ],
    },
    "gaz-naturel-europe": {
        "source": "AIE",
        "usages": [
            ("Production électrique", 38),
            ("Industrie", 28),
            ("Chauffage & bâtiment", 24),
            ("Matière première (engrais, chimie)", 8),
            ("Transport", 2),
        ],
        "products": [
            ("Chauffage domestique", "Combustible"),
            ("Électricité", "Centrale à gaz"),
            ("Engrais azoté", "Hydrogène pour l'ammoniac"),
            ("Cuisson", "Gazinière"),
            ("Plastique", "Matière première pétrochimique"),
        ],
    },
    "charbon-australie": {
        "source": "AIE",
        "usages": [
            ("Production électrique", 50),
            ("Sidérurgie", 25),
            ("Chauffage industriel", 12),
            ("Cimenterie", 8),
            ("Chimie", 5),
        ],
        "products": [
            ("Électricité", "Centrale thermique"),
            ("Acier", "Coke métallurgique"),
            ("Ciment", "Combustible de four"),
            ("Chauffage", "Combustible"),
            ("Carbochimie", "Matière première chimique"),
        ],
    },
    "ble-us-hrw": {
        "source": "FAO",
        "usages": [
            ("Alimentation humaine", 68),
            ("Alimentation animale", 19),
            ("Industrie (amidon, éthanol)", 8),
            ("Semences", 5),
        ],
        "products": [
            ("Pain", "Farine de blé"),
            ("Pâtes", "Semoule de blé"),
            ("Biscuit", "Farine"),
            ("Bière", "Maltage"),
            ("Aliment pour bétail", "Son et grains"),
        ],
    },
    "mais": {
        "source": "FAO / USDA",
        "usages": [
            ("Alimentation animale", 56),
            ("Éthanol & industrie", 30),
            ("Alimentation humaine", 12),
            ("Semences", 2),
        ],
        "products": [
            ("Aliment pour bétail", "Grain énergétique"),
            ("Éthanol", "Carburant"),
            ("Boisson sucrée", "Sirop de glucose-fructose"),
            ("Amidon de maïs", "Épaississant alimentaire"),
            ("Tortilla", "Farine de maïs"),
        ],
    },
    "riz-thai-5": {
        "source": "FAO",
        "usages": [
            ("Alimentation humaine", 85),
            ("Industrie (amidon, brasserie)", 6),
            ("Semences", 5),
            ("Alimentation animale", 4),
        ],
        "products": [
            ("Riz cuisiné", "Grain"),
            ("Galette de riz", "Farine de riz"),
            ("Bière de riz", "Fermentation"),
            ("Farine de riz", "Alternative sans gluten"),
            ("Amidon", "Industrie agroalimentaire"),
        ],
    },
    "sucre-mondial": {
        "source": "FAO / OIS",
        "usages": [
            ("Alimentation & boissons", 75),
            ("Industrie agroalimentaire", 15),
            ("Biocarburants", 8),
            ("Chimie & pharma", 2),
        ],
        "products": [
            ("Boisson sucrée", "Édulcorant"),
            ("Confiserie", "Sucre"),
            ("Pâtisserie", "Sucre"),
            ("Bioéthanol", "Carburant (canne à sucre)"),
            ("Confiture", "Agent de conservation"),
        ],
    },
    "cafe-arabica": {
        "source": "Organisation internationale du café",
        "usages": [
            ("Boisson (torréfaction)", 90),
            ("Café soluble", 8),
            ("Extraits & arômes", 2),
        ],
        "products": [
            ("Café", "Boisson torréfiée"),
            ("Café soluble", "Lyophilisat"),
            ("Capsule de café", "Café moulu"),
            ("Arôme café", "Pâtisserie et glaces"),
            ("Cosmétique", "Extrait de caféine"),
        ],
    },
    "cacao": {
        "source": "ICCO",
        "usages": [
            ("Chocolat & confiserie", 80),
            ("Boissons cacaotées", 8),
            ("Cosmétique (beurre de cacao)", 8),
            ("Biscuiterie", 4),
        ],
        "products": [
            ("Tablette de chocolat", "Pâte et beurre de cacao"),
            ("Pâte à tartiner", "Cacao"),
            ("Boisson chocolatée", "Poudre de cacao"),
            ("Cosmétique", "Beurre de cacao"),
            ("Biscuit", "Pépites de chocolat"),
        ],
    },
    "coton": {
        "source": "ICAC",
        "usages": [
            ("Textile & habillement", 60),
            ("Linge de maison", 28),
            ("Usages techniques", 10),
            ("Graines (huile, aliment)", 2),
        ],
        "products": [
            ("T-shirt", "Fibre textile"),
            ("Jean", "Denim"),
            ("Serviette de bain", "Linge de maison"),
            ("Coton hydrophile", "Usage médical"),
            ("Billet de banque", "Papier de coton"),
        ],
    },
    "soja": {
        "source": "FAO / USDA",
        "usages": [
            ("Alimentation animale", 75),
            ("Huile alimentaire", 18),
            ("Biocarburants", 5),
            ("Alimentation humaine", 2),
        ],
        "products": [
            ("Aliment pour bétail", "Tourteau de soja"),
            ("Huile de cuisson", "Huile de soja"),
            ("Tofu", "Graine de soja"),
            ("Biodiesel", "Ester d'huile de soja"),
            ("Lécithine", "Additif alimentaire (E322)"),
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
