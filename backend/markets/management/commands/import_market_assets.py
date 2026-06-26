"""Import the iMGP financial universe from the bundled CSVs into MarketAsset/AssetPrice.

CSV format (iMGP export): UTF-8 with BOM, ``;`` separator, header row, dates
``%d/%m/%Y`` in column 0 and the index level (base 100) in column 1. Idempotent —
re-running upserts the metadata and replaces each asset's price series.

Usage::

    python manage.py import_market_assets
"""

from __future__ import annotations

import csv
import datetime as dt
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction

from markets.catalog import ASSETS, AssetMeta
from markets.models import AssetPrice, MarketAsset

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"


def parse_series(path: Path) -> list[tuple[dt.date, Decimal]]:
    """Parse one iMGP CSV into ``[(date, value)]``, skipping blanks/``---``/bad rows."""
    out: list[tuple[dt.date, Decimal]] = []
    with path.open(encoding="utf-8-sig", newline="") as fh:
        reader = csv.reader(fh, delimiter=";")
        next(reader, None)  # header
        for row in reader:
            if len(row) < 2:
                continue
            raw_date, raw_value = row[0].strip(), row[1].strip()
            if not raw_date or raw_value in ("", "---"):
                continue
            try:
                date = dt.datetime.strptime(raw_date, "%d/%m/%Y").date()
                value = Decimal(raw_value)
            except (ValueError, InvalidOperation):
                continue
            out.append((date, value))
    return out


def import_asset(meta: AssetMeta, seed_dir: Path) -> int:
    """Upsert one asset and (re)load its price series. Returns the number of points."""
    asset, _ = MarketAsset.objects.update_or_create(
        code=meta.code,
        defaults={
            "name": meta.name,
            "asset_class": meta.asset_class,
            "currency": meta.currency,
            "source": "imgp_csv",
        },
    )
    series = parse_series(seed_dir / meta.path)
    asset.prices.all().delete()
    AssetPrice.objects.bulk_create(
        [AssetPrice(asset=asset, date=d, value=v) for d, v in series],
        batch_size=2000,
    )
    return len(series)


def import_all(seed_dir: Path | None = None) -> dict[str, int]:
    """Import the whole catalogue. Returns ``{code: n_points}``."""
    seed_dir = seed_dir or SEED_DIR
    stats: dict[str, int] = {}
    with transaction.atomic():
        for meta in ASSETS:
            stats[meta.code] = import_asset(meta, seed_dir)
    return stats


class Command(BaseCommand):
    help = "Importe les indices financiers iMGP (CSV) dans MarketAsset/AssetPrice."

    def handle(self, *args, **options):
        stats = import_all()
        total = sum(stats.values())
        for code, n in stats.items():
            self.stdout.write(f"  {code:10s} {n:>5d} points")
        self.stdout.write(
            self.style.SUCCESS(f"{len(stats)} actifs importés, {total} points au total.")
        )
