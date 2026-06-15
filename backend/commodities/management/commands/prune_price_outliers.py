"""Detect (and with --apply, delete) absurd price quotes.

A bad quote is one that deviates more than --factor× from its **local** neighbours
(a rolling median of the nearby points in time), e.g. a feed that returned the
commodity in the wrong currency, producing isolated ~10× spikes (seen on PVC).

The comparison is LOCAL on purpose: a global median would wrongly flag legitimate
long-term trends (gold went 20× since the 1960s) or real brief events. Dry-run by
default; pass --apply to delete.

    python manage.py prune_price_outliers            # report only
    python manage.py prune_price_outliers --apply    # delete the outliers
"""

from __future__ import annotations

from decimal import Decimal
from statistics import median

from django.core.management.base import BaseCommand

from commodities.models import Commodity, PriceQuote

# Half-window (in points) for the local median — wide enough that a short bad
# plateau stays a minority, narrow enough to track the price trend.
_WINDOW = 30


class Command(BaseCommand):
    help = "Détecte/supprime les cours aberrants (écart × la médiane LOCALE). --apply pour supprimer."

    def add_arguments(self, parser):
        parser.add_argument("--factor", type=float, default=5.0, help="Seuil (× la médiane locale).")
        parser.add_argument("--apply", action="store_true", help="Supprimer (sinon dry-run).")

    def handle(self, *args, **options) -> None:
        factor = Decimal(str(options["factor"]))
        apply = options["apply"]
        total = 0
        for commodity in Commodity.objects.filter(is_active=True).order_by("name"):
            rows = list(commodity.prices.order_by("date").values_list("id", "price_usd"))
            n = len(rows)
            if n < 8:
                continue  # too few points to judge
            prices = [v for _, v in rows]
            bad: list[int] = []
            for i in range(n):
                window = prices[max(0, i - _WINDOW) : i + _WINDOW + 1]
                med = median(window)
                if med > 0 and (prices[i] > med * factor or prices[i] < med / factor):
                    bad.append(rows[i][0])
            if not bad:
                continue
            total += len(bad)
            self.stdout.write(f"  {commodity.name}: {len(bad)} aberrant(s) sur {n}")
            if apply:
                PriceQuote.objects.filter(id__in=bad).delete()
        verb = "supprimés" if apply else "détectés (dry-run — ajoute --apply pour supprimer)"
        self.stdout.write(self.style.SUCCESS(f"{total} cours aberrants {verb}."))
