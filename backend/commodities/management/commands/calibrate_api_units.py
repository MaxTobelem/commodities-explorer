"""Calibrate Commodities-API unit factors for *candidate* daily tickers.

For each commodity that's currently World-Bank-only, this fetches the API's native
price (1/rate, no factor applied) and compares it to the latest stored World Bank
price, printing the **implied unit factor** (= WB / native). That factor is what
must go into ``commodities_api._UNIT_FACTOR`` before mapping the ticker — otherwise
the daily price would be in the wrong unit. Read-only; needs COMMODITIES_API_KEY.

    python manage.py calibrate_api_units

A clean implied factor (≈1, ≈0.001, ≈2.205, ≈0.4536…) ⇒ a fixed unit conversion,
safe to map. A "messy"/non-constant factor usually means the symbol is quoted in a
foreign currency (FX varies daily) ⇒ a static factor can't track it; leave on WB.
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from commodities.datasources.commodities_api import CommoditiesApiProvider
from commodities.models import Commodity

# Candidate slug → best-guess Commodities-API ticker (from /symbols). Bois (grumes)
# is omitted: no log/roundwood ticker exists (only sawnwood/lumber).
CANDIDATES: dict[str, str] = {
    "gaz-naturel-europe": "EU-NG",
    "gnl-japon": "LNG-J",
    "huile-de-palme": "CPO",
    "huile-de-soja": "ZL",
    "huile-de-tournesol": "SUN-OIL",
    "orge": "NBLC1",
    "the": "TEA",
    "banane": "BANA-US",
    "boeuf": "BEEF",
    "crevettes": "SHRIMP",
    "caoutchouc": "RUBBER",
    "phosphate-roche": "PHSP",
    "dap-engrais": "DI_AMMON",
    "uree": "UREA",
    "chlorure-de-potassium": "POT-CHL",
    "tabac": "TOBACCO",
    # --- Nouveaux candidats (tops + secondaires). Pas dans World Bank pour la plupart,
    # donc pas de facteur calculé : on affiche le cours natif API, à interpréter à la
    # main (magnitude + prix de marché connu) pour fixer l'unité canonique + le facteur.
    # Énergie
    "uranium": "URANIUM",
    "petrole-brut-wti": "WTIOIL",
    "diesel": "US-D",
    "essence": "RB00",
    "ethanol": "ETHANOL",
    "propane": "PROPANE",
    "naphta": "NAPHTHA",
    "methanol": "METHANOL",
    # Précieux / batterie / critiques
    "palladium": "XPD",
    "rhodium": "XRH",
    "carbonate-de-lithium": "LITH-CAR",
    "manganese": "MN",
    "molybdene": "MO",
    "magnesium": "MG",
    "titane": "TITANIUM",
    "tungstene": "TUNGSTEN",
    "gallium": "GALLIUM",
    "germanium": "GER",
    "antimoine": "ANTIMONY",
    "neodyme": "ND",
    "dysprosium": "DYS",
    # Acier
    "acier-hrc": "US-HRC",
    "ferraille": "SCRAP-HM",
    "ferrochrome": "FE-CR",
    "ferrosilicium": "FE-SI",
    # Agricole / élevage
    "colza": "CANO",
    "porc": "LHOG",
    "cafe-robusta": "ROBUSTA",
    "jus-d-orange": "ORANGE",
    "avoine": "OATS",
    "laine": "WOOL",
    "saumon": "SALMON",
    "huile-de-coco": "COCO-OIL",
    # Industrie / chimie
    "polyethylene": "PE",
    "polypropylene": "PP",
    "pvc": "PVC",
    "soude": "SODA-ASH",
    "pate-a-papier": "KRAFT-PU",
}

# Known clean factors to suggest a match for the implied ratio.
_TROY_OZ_PER_TONNE = Decimal("32150.7466")
_LB_PER_KG = Decimal("2.2046226218")
_KNOWN: dict[str, Decimal] = {
    "1 (déjà canonique)": Decimal(1),
    "0.001 (USD/t → USD/kg)": Decimal("0.001"),
    "1000 (USD/kg → USD/t)": Decimal(1000),
    "2.2046 (USD/lb → USD/kg)": _LB_PER_KG,
    "0.02205 (cents/lb → USD/kg)": _LB_PER_KG / 100,
    "32150.7 (USD/ozt → USD/t)": _TROY_OZ_PER_TONNE,
}


def _nearest_known(factor: Decimal) -> str:
    """Closest known conversion (by ratio) — a hint for what _UNIT_FACTOR to set."""
    best, best_ratio = "—", None
    for label, value in _KNOWN.items():
        ratio = float(factor / value)
        dist = abs(ratio - 1)
        if best_ratio is None or dist < best_ratio:
            best, best_ratio = label, dist
    return f"{best}  (écart {best_ratio * 100:.0f}%)" if best_ratio is not None else "—"


class Command(BaseCommand):
    help = (
        "Calibre les facteurs d'unité Commodities-API pour les matières mensuelles (vs World Bank)."
    )

    def handle(self, *args, **options) -> None:
        provider = CommoditiesApiProvider()
        if not provider.api_key:
            raise CommandError("COMMODITIES_API_KEY manquant — configurez la clé.")

        # Native price = 1/rate with factor 1 (the candidate tickers aren't in
        # _UNIT_FACTOR), obtained by querying as throwaway commodities.
        probes = [Commodity(slug=s, name=s, api_symbol=t) for s, t in CANDIDATES.items()]
        native = {pd.commodity.slug: pd.price_usd for pd in provider.fetch_latest(probes)}

        self.stdout.write(
            self.style.MIGRATE_HEADING("matière | ticker | natif API | WB | facteur implicite")
        )
        for slug, ticker in CANDIDATES.items():
            nat = native.get(slug)
            commodity = Commodity.objects.filter(slug=slug).first()
            quote = commodity.prices.order_by("-date").first() if commodity else None
            if nat is None:
                self.stdout.write(
                    self.style.ERROR(f"  {slug}: {ticker} — API ne renvoie aucun cours")
                )
                continue
            if quote is None:
                self.stdout.write(
                    self.style.WARNING(
                        f"  {slug}: {ticker} natif={nat} — aucun cours WB pour comparer"
                    )
                )
                continue
            factor = quote.price_usd / nat if nat else Decimal(0)
            unit = commodity.price_unit
            self.stdout.write(
                f"  {slug}: {ticker} | natif={nat} | WB={quote.price_usd} {unit} ({quote.source} {quote.date}) "
                f"| facteur≈{factor:.6f} → {_nearest_known(factor)}"
            )
