"""Orchestration of data imports.

These functions are the single entry point used by both the management commands
(cron) and the admin "run update" action. Each wraps its work in an ImportRun so
progress/outcome is visible and auditable.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from statistics import median

from django.db import transaction
from django.db.models import Q
from django.utils import timezone
from django.utils.text import slugify

from .countries import french_name
from .datasources.base import EnrichmentResult
from .datasources.registry import get_enrichment_providers, get_price_provider
from .models import (
    Commodity,
    CommodityProduction,
    CommodityReserve,
    CommodityUsage,
    Country,
    Event,
    EventImpact,
    ImportRun,
    PriceQuote,
    Product,
    ProductComposition,
    Sector,
)

# A new daily quote deviating more than this factor from the commodity's recent
# median is treated as bad upstream data (e.g. a feed returning the wrong currency,
# which produced ~10× spikes on PVC) and rejected. Legit daily moves never approach it.
PRICE_OUTLIER_FACTOR = 5

# News-event sources (everything refresh_events manages). Used to scope the
# retention purge so it never touches USGS/OWID/RMIS/curated qualitative rows.
NEWS_SOURCES = ("presse", "mining", "gnews", "gdelt")
# Rolling archive: refresh_events keeps this many days of news (by article date)
# instead of wiping the whole set each run, so recent articles survive after they
# drop out of the RSS feeds. Older (or undated) news no longer in the feed is purged.
EVENT_RETENTION_DAYS = 31


def update_prices() -> ImportRun:
    """Fetch and upsert the latest price quotes for all active commodities.

    Two lanes, in order:
      1. **Commodities-API (daily)** for commodities carrying an ``api_symbol``,
         when ``COMMODITIES_API_KEY`` is configured. A provider/API failure
         aborts the run (a broken paid subscription should be loud, not stale).
      2. **Historical/fallback provider** (``price_provider``, e.g. World Bank
         monthly) fills in whatever lane 1 did not price — so a missing or
         unknown ticker degrades gracefully to the free source, never a gap.

    Idempotent: re-running on the same day updates existing quotes (keyed by
    commodity+date+source) rather than creating duplicates.
    """
    from django.conf import settings

    run = ImportRun.objects.create(kind=ImportRun.Kind.PRICES)
    try:
        commodities = list(Commodity.objects.filter(is_active=True))
        created = updated = rejected = 0
        priced_ids: set[int] = set()
        missing_providers: set[str] = set()
        rejected_names: set[str] = set()

        # Sanity baseline: median of each commodity's recent quotes (last 90 days).
        # A new point outside ±PRICE_OUTLIER_FACTOR× the median is rejected as bad
        # upstream data (so a wrong-currency spike never lands, nor recurs daily).
        cutoff = dt.date.today() - dt.timedelta(days=90)
        recent: dict[int, list] = defaultdict(list)
        for cid, val in PriceQuote.objects.filter(date__gte=cutoff).values_list(
            "commodity_id", "price_usd"
        ):
            recent[cid].append(val)
        medians = {cid: median(vals) for cid, vals in recent.items() if len(vals) >= 5}

        def upsert(price) -> None:
            nonlocal created, updated, rejected
            med = medians.get(price.commodity.pk)
            if med and not (
                med / PRICE_OUTLIER_FACTOR <= price.price_usd <= med * PRICE_OUTLIER_FACTOR
            ):
                rejected += 1
                rejected_names.add(price.commodity.name)
                return  # absurd vs history → skip (keeps the previous good quote)
            _, was_created = PriceQuote.objects.update_or_create(
                commodity=price.commodity,
                date=price.date,
                source=price.source,
                defaults={"price_usd": price.price_usd, "price_eur": price.price_eur},
            )
            created += int(was_created)
            updated += int(not was_created)
            priced_ids.add(price.commodity.pk)

        # Lane 1 — Commodities-API (daily updates via api_symbol).
        api_provider = get_price_provider("commodities_api")
        api_ready = api_provider is not None and bool(
            getattr(settings, "COMMODITIES_API_KEY", "")
        )
        if api_ready:
            api_items = [c for c in commodities if c.api_symbol]
            if api_items:
                for price in api_provider.fetch_latest(api_items):
                    upsert(price)

        # Lane 2 — historical/fallback provider for whatever is still unpriced.
        remaining = [c for c in commodities if c.pk not in priced_ids]
        by_provider: dict[str, list[Commodity]] = defaultdict(list)
        for commodity in remaining:
            by_provider[commodity.price_provider].append(commodity)
        for provider_key, items in by_provider.items():
            provider = get_price_provider(provider_key)
            if provider is None:
                missing_providers.add(provider_key)
                continue
            for price in provider.fetch_latest(items):
                upsert(price)

        skipped = len(commodities) - len(priced_ids)
        message = (
            f"{created} cours créés, {updated} mis à jour, {skipped} matières sans prix."
        )
        if rejected:
            message += f" {rejected} cours aberrants rejetés ({', '.join(sorted(rejected_names))})."
        if missing_providers:
            message += f" Fournisseurs inconnus: {', '.join(sorted(missing_providers))}."
        run.finish(ImportRun.Status.SUCCESS, message)
    except Exception as exc:  # noqa: BLE001 — surface any failure into the audit row
        run.finish(ImportRun.Status.ERROR, f"{type(exc).__name__}: {exc}")
    return run


def backfill_prices(days: int = 90) -> ImportRun:
    """Backfill historical daily prices (providers that support time series)."""
    run = ImportRun.objects.create(kind=ImportRun.Kind.PRICES)
    try:
        end = dt.date.today()
        start = end - dt.timedelta(days=days)
        commodities = list(Commodity.objects.filter(is_active=True))
        by_provider: dict[str, list[Commodity]] = defaultdict(list)
        for commodity in commodities:
            by_provider[commodity.price_provider].append(commodity)

        to_upsert: list[PriceQuote] = []
        for provider_key, items in by_provider.items():
            provider = get_price_provider(provider_key)
            if provider is None or not hasattr(provider, "fetch_timeseries"):
                continue
            for price in provider.fetch_timeseries(items, start, end):
                to_upsert.append(
                    PriceQuote(
                        commodity=price.commodity,
                        date=price.date,
                        source=price.source,
                        price_usd=price.price_usd,
                        price_eur=price.price_eur,
                    )
                )
        if to_upsert:
            # Bulk upsert (handles tens of thousands of historical points fast).
            PriceQuote.objects.bulk_create(
                to_upsert,
                batch_size=1000,
                update_conflicts=True,
                unique_fields=["commodity", "date", "source"],
                update_fields=["price_usd", "price_eur"],
            )

        run.finish(
            ImportRun.Status.SUCCESS,
            f"Backfill {start}→{end} : {len(to_upsert)} cours importés.",
        )
    except Exception as exc:  # noqa: BLE001
        run.finish(ImportRun.Status.ERROR, f"{type(exc).__name__}: {exc}")
    return run


def backfill_daily(days: int = 30, missing: bool = False) -> ImportRun:
    """Backfill recent DAILY prices from Commodities-API for commodities carrying an
    ``api_symbol`` — fills the gap between the monthly World Bank history and today.

    With ``missing=True``, only commodities whose Commodities-API history doesn't yet
    reach back to ``start`` are fetched (i.e. newly-mapped tickers), so re-running
    doesn't re-spend API quota on ranges already ingested.
    """
    from django.conf import settings

    run = ImportRun.objects.create(kind=ImportRun.Kind.PRICES)
    try:
        provider = get_price_provider("commodities_api")
        if provider is None or not getattr(settings, "COMMODITIES_API_KEY", ""):
            run.finish(
                ImportRun.Status.ERROR,
                "COMMODITIES_API_KEY manquant — backfill quotidien impossible.",
            )
            return run
        end = dt.date.today()
        start = end - dt.timedelta(days=days)
        commodities = [c for c in Commodity.objects.filter(is_active=True) if c.api_symbol]
        if missing:
            # Keep only commodities lacking daily history back to `start` (no quote on or
            # before it) — the newly-mapped tickers — so we don't re-request ranges that
            # are already ingested. A single recent quote (e.g. today's update_prices)
            # doesn't count as covered.
            covered = set(
                PriceQuote.objects.filter(
                    source="commodities_api", commodity__in=commodities, date__lte=start
                )
                .values_list("commodity_id", flat=True)
                .distinct()
            )
            commodities = [c for c in commodities if c.id not in covered]
        if not commodities:
            run.finish(
                ImportRun.Status.SUCCESS,
                f"Aucune matière à backfiller (historique déjà couvert jusqu'au {start}).",
            )
            return run

        # Persist each commodity's points as they arrive (the provider yields symbol
        # by symbol) so a mid-run rate-limit/abort never discards the requests already
        # spent — the upstream caps at 60 req/min.
        saved = 0
        batch: list[PriceQuote] = []

        def flush() -> None:
            nonlocal saved
            if not batch:
                return
            PriceQuote.objects.bulk_create(
                batch,
                batch_size=1000,
                update_conflicts=True,
                unique_fields=["commodity", "date", "source"],
                update_fields=["price_usd", "price_eur"],
            )
            saved += len(batch)
            batch.clear()

        fetch_error: Exception | None = None
        try:
            for p in provider.fetch_timeseries(commodities, start, end):
                batch.append(
                    PriceQuote(
                        commodity=p.commodity,
                        date=p.date,
                        source=p.source,
                        price_usd=p.price_usd,
                        price_eur=p.price_eur,
                    )
                )
                if len(batch) >= 500:
                    flush()
        except Exception as exc:  # noqa: BLE001 — keep partial progress, then report
            fetch_error = exc
        flush()

        if fetch_error is not None:
            run.finish(
                ImportRun.Status.ERROR,
                f"Backfill interrompu : {saved} cours sauvegardés avant l'erreur "
                f"({type(fetch_error).__name__}: {fetch_error}).",
            )
            return run

        # /timeseries is one symbol per request, split into ≤max_days windows; report
        # the resulting request count so API-quota usage stays visible in the audit.
        max_days = getattr(provider, "timeseries_max_days", 30)
        windows = (days + max_days + 1) // (max_days + 1)
        n_requests = (len(commodities) + 1) * windows
        run.finish(
            ImportRun.Status.SUCCESS,
            f"Backfill quotidien {start}→{end} : {saved} cours "
            f"Commodities-API importés ({windows} fenêtre(s) × {len(commodities) + 1} "
            f"symboles ≈ {n_requests} requêtes API).",
        )
    except Exception as exc:  # noqa: BLE001
        run.finish(ImportRun.Status.ERROR, f"{type(exc).__name__}: {exc}")
    return run


def enrich_data(kind: str = ImportRun.Kind.ENRICH) -> ImportRun:
    """Run all enrichment providers and upsert their records (monthly cadence).

    Per-provider failures are isolated so one bad source doesn't abort the rest.
    Qualitative rows (usages/compositions/impacts) are tagged needs_review for
    admin validation; reserves/production are authoritative.
    """
    run = ImportRun.objects.create(kind=kind)
    try:
        commodities = list(Commodity.objects.filter(is_active=True))
        merged = EnrichmentResult()
        provider_errors: list[str] = []
        for provider in get_enrichment_providers():
            try:
                merged.extend(provider.fetch(commodities))
            except Exception as exc:  # noqa: BLE001 — isolate per-source failures
                provider_errors.append(f"{provider.key}: {type(exc).__name__}")

        counts = _apply_enrichment(merged)
        message = (
            f"{counts['production']} productions, {counts['reserves']} réserves, "
            f"{counts['usages']} usages, {counts['compositions']} compositions, "
            f"{counts['impacts']} impacts."
        )
        if provider_errors:
            message += " Avertissements: " + "; ".join(provider_errors)
        run.finish(ImportRun.Status.SUCCESS, message)
    except Exception as exc:  # noqa: BLE001
        run.finish(ImportRun.Status.ERROR, f"{type(exc).__name__}: {exc}")
    return run


def refresh_events(kind: str = ImportRun.Kind.ENRICH) -> ImportRun:
    """Refresh commodity news events — lighter than enrich_data, for a daily cron
    (news moves faster than the annual USGS/RMIS data).

    Two coordinated sources: **presse** (curated publisher RSS) is primary because
    its articles carry real summaries; **gnews** (Google News) then fills only the
    commodities presse didn't cover (most metals, tropical softs, niche goods).

    Rolling archive (EVENT_RETENTION_DAYS): the fresh articles are upserted, then
    news older than the window (or undated) that is *no longer in the current feed*
    is purged — so the last ~month of news is kept even after articles fall out of
    the RSS feeds, without the table growing without bound. A failed fetch (no
    impacts) keeps the existing events untouched.
    """
    run = ImportRun.objects.create(kind=kind)
    try:
        commodities = list(Commodity.objects.filter(is_active=True))
        providers = {p.key: p for p in get_enrichment_providers()}
        merged = EnrichmentResult()
        errors: list[str] = []

        covered: set[str] = set()
        for key in ("presse", "mining"):  # primary sources — real article summaries
            provider = providers.get(key)
            if provider is None:
                continue
            try:
                res = provider.fetch(commodities)
                merged.extend(res)
                covered |= {im.commodity.slug for im in res.impacts}
            except Exception as exc:  # noqa: BLE001 — isolate the source failure
                errors.append(f"{key}: {type(exc).__name__}")

        gnews = providers.get("gnews")
        if gnews is not None:
            gap = [c for c in commodities if c.slug not in covered]
            try:
                merged.extend(gnews.fetch(gap))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"gnews: {type(exc).__name__}")

        with transaction.atomic():
            # Upsert first so recurring articles get their dates refreshed before we
            # decide what's stale (and so they land in the "keep" set below).
            counts = _apply_enrichment(merged)
            if merged.impacts:
                fresh_slugs = {slugify(rec.event_title) for rec in merged.impacts}
                cutoff = timezone.now().date() - dt.timedelta(days=EVENT_RETENTION_DAYS)
                # Purge news past the retention window (or undated) that is no longer
                # surfaced by the feeds. Collect ids first: .distinct().delete() is
                # disallowed, and the impacts join can duplicate event rows.
                stale = list(
                    Event.objects.filter(impacts__source__in=NEWS_SOURCES)
                    .filter(Q(start_date__lt=cutoff) | Q(start_date__isnull=True))
                    .exclude(slug__in=fresh_slugs)
                    .values_list("id", flat=True)
                    .distinct()
                )
                Event.objects.filter(id__in=stale).delete()
        message = f"{counts['impacts']} actualités (presse + mining + Google News)."
        if counts["skipped"]:
            message += f" {counts['skipped']} ignorée(s) (données invalides)."
        if errors:
            message += " Avertissements: " + "; ".join(errors)
        run.finish(ImportRun.Status.SUCCESS, message)
    except Exception as exc:  # noqa: BLE001
        run.finish(ImportRun.Status.ERROR, f"{type(exc).__name__}: {exc}")
    return run


@transaction.atomic
def _apply_enrichment(result: EnrichmentResult) -> dict[str, int]:
    counts = {
        "production": 0,
        "reserves": 0,
        "usages": 0,
        "compositions": 0,
        "impacts": 0,
        "skipped": 0,
    }
    country_cache: dict[str, Country] = {}

    def country_for(iso3: str, name: str) -> Country:
        if iso3 not in country_cache:
            country_cache[iso3], _ = Country.objects.get_or_create(
                iso3=iso3, defaults={"name": french_name(iso3, name)}
            )
        return country_cache[iso3]

    for rec in result.production:
        CommodityProduction.objects.update_or_create(
            commodity=rec.commodity,
            country=country_for(rec.country_iso3, rec.country_name),
            year=rec.year,
            defaults={
                "production_t": rec.production_t,
                "unit": rec.unit,
                "note": rec.note,
                "source": rec.source,
            },
        )
        counts["production"] += 1

    for rec in result.reserves:
        CommodityReserve.objects.update_or_create(
            commodity=rec.commodity,
            country=country_for(rec.country_iso3, rec.country_name),
            year=rec.year,
            defaults={"reserves_t": rec.reserves_t, "unit": rec.unit, "source": rec.source},
        )
        counts["reserves"] += 1

    for rec in result.usages:
        sector, _ = Sector.objects.get_or_create(
            slug=slugify(rec.sector_name),
            defaults={"name": rec.sector_name, "nace_code": rec.nace_code},
        )
        CommodityUsage.objects.update_or_create(
            commodity=rec.commodity,
            sector=sector,
            defaults={
                "share_percent": rec.share_percent,
                "description": rec.description,
                "source": rec.source,
                "needs_review": True,
            },
        )
        counts["usages"] += 1

    for rec in result.compositions:
        product, _ = Product.objects.get_or_create(
            slug=slugify(rec.product_name), defaults={"name": rec.product_name}
        )
        ProductComposition.objects.update_or_create(
            commodity=rec.commodity,
            product=product,
            defaults={"role": rec.role, "source": rec.source, "needs_review": True},
        )
        counts["compositions"] += 1

    for rec in result.impacts:
        # update_or_create (not get_or_create) so re-runs refresh the date/description
        # — news events are living signals, not rows frozen at first import.
        # Per-record savepoint: one pathological article (oversized value, bad data)
        # must never abort the whole news refresh — skip it and keep the rest.
        # (A DataError without a savepoint poisons the surrounding transaction.)
        try:
            with transaction.atomic():
                event, _ = Event.objects.update_or_create(
                    slug=slugify(rec.event_title),
                    defaults={
                        "title": rec.event_title,
                        "type": rec.event_type,
                        "start_date": rec.start_date,
                        "description": rec.description,
                        "source_url": rec.source_url,
                    },
                )
                EventImpact.objects.update_or_create(
                    event=event,
                    commodity=rec.commodity,
                    defaults={
                        "direction": rec.direction,
                        "magnitude": rec.magnitude,
                        "source": rec.source,
                        "needs_review": True,
                    },
                )
            counts["impacts"] += 1
        except Exception:  # noqa: BLE001 — drop the bad record, keep the batch alive
            counts["skipped"] += 1

    return counts
