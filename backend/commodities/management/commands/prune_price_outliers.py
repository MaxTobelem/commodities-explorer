"""Detect (and with --apply, delete) absurd price quotes.

Points that deviate more than --factor× from a commodity's median are almost
always bad upstream data — e.g. a feed that returned the commodity in the wrong
currency, producing ~10× spikes in the backfilled history (seen on PVC). Dry-run
by default; pass --apply to delete. Use this to clean existing data and to see
which commodities are affected.

    python manage.py prune_price_outliers            # report only
    python manage.py prune_price_outliers --apply    # delete the outliers
"""

from __future__ import annotations

from decimal import Decimal
from statistics import median

from django.core.management.base import BaseCommand

from commodities.models import Commodity, PriceQuote


class Command(BaseCommand):
    help = "Détecte/supprime les cours aberrants (écart × la médiane). --apply pour supprimer."

    def add_arguments(self, parser):
        parser.add_argument("--factor", type=float, default=5.0, help="Seuil (× la médiane).")
        parser.add_argument("--apply", action="store_true", help="Supprimer (sinon dry-run).")

    def handle(self, *args, **options) -> None:
        factor = Decimal(str(options["factor"]))
        apply = options["apply"]
        total = 0
        for commodity in Commodity.objects.filter(is_active=True).order_by("name"):
            rows = list(commodity.prices.values_list("id", "price_usd"))
            if len(rows) < 10:
                continue  # too few points for a reliable median
            med = median(v for _, v in rows)
            if med <= 0:
                continue
            hi, lo = med * factor, med / factor
            bad = [pid for pid, v in rows if v > hi or v < lo]
            if not bad:
                continue
            total += len(bad)
            self.stdout.write(
                f"  {commodity.name}: médiane {med:.2f} {commodity.price_unit} — "
                f"{len(bad)} aberrant(s) sur {len(rows)}"
            )
            if apply:
                PriceQuote.objects.filter(id__in=bad).delete()
        verb = "supprimés" if apply else "détectés (dry-run — ajoute --apply pour supprimer)"
        self.stdout.write(self.style.SUCCESS(f"{total} cours aberrants {verb}."))
