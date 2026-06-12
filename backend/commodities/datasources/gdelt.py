"""GDELT event provider — bulk daily Events export (no rate-limited API).

GDELT's public DOC API throttles hard per-IP, which made a cron unreliable
(empty runs were a coin-flip). Instead we download GDELT 1.0's **daily Events
export** — one CSV per day, ~7 MB zipped, plain HTTP, *not* rate-limited — keep
the material-conflict events (CAMEO QuadClass 4) located in our producing
countries, and turn each country's aggregate into a candidate supply-impacting
``Tensions en {pays}`` event, tagged needs_review for admin validation.

No machine translation: the description is built from the CAMEO root code, which
we map directly to a French label. Each event also carries a real source-article
URL (GDELT's SOURCEURL column).
"""

from __future__ import annotations

import csv
import datetime as dt
import io
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from typing import TYPE_CHECKING

import requests
from django.conf import settings
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from commodities.models import CommodityProduction, Event, EventImpact

from .base import EnrichmentProvider, EnrichmentResult, ImpactRecord

if TYPE_CHECKING:
    from commodities.models import Commodity, Country

# GDELT 1.0 daily Events export: <base>/YYYYMMDD.export.CSV.zip
GDELT_EVENTS_URL = "http://data.gdeltproject.org/events"
USER_AGENT = "commodities-explorer/1.0 (research dashboard)"

# Column indices in the GDELT 1.0 Event record (0-based; 58 tab-separated fields).
_SQLDATE = 1
_EVENT_ROOT = 28
_QUADCLASS = 29
_NUM_ARTICLES = 33
_ACTIONGEO_CC = 51  # ActionGeo_CountryCode (FIPS 10-4, 2-letter)
_DATEADDED = 56  # YYYYMMDD the event was ingested (= the file's day → freshness anchor)
_SOURCEURL = 57  # last column
_MIN_FIELDS = 58

_QUAD_MATERIAL_CONFLICT = "4"

# CAMEO EventRootCode → French label (QuadClass 4 = material conflict, roots 14–20).
_ROOT_FR = {
    "14": "Manifestations et protestations",
    "15": "Démonstrations de force",
    "16": "Rupture de relations",
    "17": "Mesures coercitives",
    "18": "Agressions",
    "19": "Affrontements armés",
    "20": "Violences de masse",
}
_ROOT_FALLBACK = "Tensions signalées"

# FIPS 10-4 (GDELT ActionGeo_CountryCode) → ISO 3166-1 alpha-3.
# Curated for commodity-producing countries; mind the FIPS/ISO false-friends
# (FIPS CH=China, RS=Russia, AS=Australia, AU=Austria, GM=Germany, NI=Nigeria,
# ZA=Zambia, SF=South Africa, MU=Oman, BM=Myanmar, CE=Sri Lanka…) — these were
# verified against real ActionGeo_FullName values before being added.
_FIPS_TO_ISO3 = {
    # Americas
    "US": "USA", "CA": "CAN", "MX": "MEX", "BR": "BRA", "AR": "ARG",
    "CI": "CHL", "PE": "PER", "BL": "BOL", "VE": "VEN", "CO": "COL",
    "EC": "ECU", "GY": "GUY", "NS": "SUR", "PA": "PRY", "PM": "PAN",
    "CU": "CUB", "DR": "DOM", "JM": "JAM", "HO": "HND", "GT": "GTM",
    "TD": "TTO", "UY": "URY",
    # Europe
    "FR": "FRA", "GM": "DEU", "UK": "GBR", "SP": "ESP", "IT": "ITA",
    "PL": "POL", "PO": "PRT", "SW": "SWE", "SZ": "CHE", "NO": "NOR",
    "FI": "FIN", "AU": "AUT", "EZ": "CZE", "LO": "SVK", "SI": "SVN",
    "HU": "HUN", "RO": "ROU", "BU": "BGR", "GR": "GRC", "EN": "EST",
    "LG": "LVA", "LH": "LTU", "UP": "UKR", "RS": "RUS", "BO": "BLR",
    "RB": "SRB", "IC": "ISL", "EI": "IRL", "NL": "NLD", "BE": "BEL",
    "AL": "ALB", "MK": "MKD", "MD": "MDA",
    # Middle East / Caucasus / Central Asia
    "IR": "IRN", "IS": "ISR", "SA": "SAU", "AE": "ARE", "IZ": "IRQ",
    "KU": "KWT", "QA": "QAT", "MU": "OMN", "BA": "BHR", "JO": "JOR",
    "LE": "LBN", "SY": "SYR", "YM": "YEM", "TU": "TUR", "AM": "ARM",
    "GG": "GEO", "AJ": "AZE", "KZ": "KAZ", "TI": "TJK", "TX": "TKM",
    "UZ": "UZB", "KG": "KGZ", "AF": "AFG", "PK": "PAK",
    # Asia-Pacific
    "CH": "CHN", "IN": "IND", "ID": "IDN", "JA": "JPN", "KS": "KOR",
    "KN": "PRK", "TW": "TWN", "MY": "MYS", "TH": "THA", "VM": "VNM",
    "RP": "PHL", "BM": "MMR", "CB": "KHM", "LA": "LAO", "BG": "BGD",
    "CE": "LKA", "MG": "MNG", "NP": "NPL", "PP": "PNG", "NC": "NCL",
    "AS": "AUS", "NZ": "NZL",
    # Africa
    "SF": "ZAF", "NI": "NGA", "NG": "NER", "CG": "COD", "CF": "COG",
    "GH": "GHA", "GV": "GIN", "ML": "MLI", "MO": "MAR", "MA": "MDG",
    "WA": "NAM", "ZA": "ZMB", "ZI": "ZWE", "TZ": "TZA", "MZ": "MOZ",
    "AO": "AGO", "EG": "EGY", "LY": "LBY", "AG": "DZA", "TS": "TUN",
    "SU": "SDN", "SG": "SEN", "IV": "CIV", "KE": "KEN", "UG": "UGA",
    "ET": "ETH", "BC": "BWA", "WZ": "SWZ", "LT": "LSO", "MI": "MWI",
    "CM": "CMR", "GB": "GAB", "CD": "TCD",
}

# Network session with retry/back-off (the VPS occasionally sees transient
# "Network is unreachable" to public CDNs).
_RETRY = Retry(
    total=3,
    connect=3,
    read=3,
    backoff_factor=1.5,
    status_forcelist=(500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
)


def _session() -> requests.Session:
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=_RETRY)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session


def _to_int(value: str) -> int:
    try:
        return int(value)
    except (ValueError, TypeError):
        return 0


def _parse_date(raw: str) -> dt.date | None:
    try:
        return dt.datetime.strptime(str(raw)[:8], "%Y%m%d").date()
    except (ValueError, TypeError):
        return None


class GdeltProvider(EnrichmentProvider):
    key = "gdelt"

    @property
    def base_url(self) -> str:
        return getattr(settings, "GDELT_EVENTS_URL", GDELT_EVENTS_URL)

    @property
    def lookback_days(self) -> int:
        # How many recent daily files to scan (starting yesterday). More days =
        # broader, steadier coverage; one daily file ≈ 7 MB.
        return getattr(settings, "GDELT_LOOKBACK_DAYS", 3)

    @property
    def min_articles(self) -> int:
        # A producing country must accumulate at least this many material-conflict
        # articles over the window to be flagged (tuned against real GDELT volume).
        return getattr(settings, "GDELT_MIN_ARTICLES", 3000)

    @property
    def max_countries(self) -> int:
        # Top-N producing countries per commodity considered for a signal.
        return getattr(settings, "GDELT_MAX_COUNTRIES", 2)

    @property
    def timeout(self) -> int:
        return getattr(settings, "GDELT_TIMEOUT", 30)

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        # Map each producing country (a top-N producer of some commodity) to the
        # commodities it would impact, so one country signal fans out correctly.
        commodities_by_iso3: dict[str, list[Commodity]] = defaultdict(list)
        country_by_iso3: dict[str, Country] = {}
        for commodity in commodities:
            top = (
                CommodityProduction.objects.filter(commodity=commodity)
                .order_by("-production_t")
                .select_related("country")[: self.max_countries]
            )
            for production in top:
                iso3 = production.country.iso3
                commodities_by_iso3[iso3].append(commodity)
                country_by_iso3[iso3] = production.country
        if not commodities_by_iso3:
            return EnrichmentResult()

        # Only FIPS codes that resolve to one of our producing countries matter.
        wanted_fips = {
            fips: iso3 for fips, iso3 in _FIPS_TO_ISO3.items() if iso3 in commodities_by_iso3
        }
        signals = self._scan_conflicts(wanted_fips)

        result = EnrichmentResult()
        year = dt.date.today().year
        for iso3, signal in signals.items():
            country = country_by_iso3[iso3]
            label = _ROOT_FR.get(signal["root"], _ROOT_FALLBACK)
            description = (
                f"{label} — {signal['articles']} articles recensés "
                f"sur {self.lookback_days} j (source GDELT)."
            )
            for commodity in commodities_by_iso3[iso3]:
                result.impacts.append(
                    ImpactRecord(
                        commodity=commodity,
                        event_title=f"Tensions en {country.name} ({year})",
                        event_type=Event.Type.WAR,
                        start_date=signal["date"] or dt.date.today(),
                        description=description,
                        source_url=signal["url"],
                        direction=EventImpact.Direction.UP,
                        magnitude=None,
                        source=self.key,
                    )
                )
        return result

    # -- internals -----------------------------------------------------------

    def _scan_conflicts(self, wanted_fips: dict[str, str]) -> dict[str, dict]:
        """Aggregate material-conflict events per producing country over the window.

        Per country we keep the running article total and the single most-covered
        event (its CAMEO root → French label, its SOURCEURL, its date) as the
        representative. Countries below ``min_articles`` are dropped.
        """
        agg: dict[str, dict] = {}
        for file_date in self._recent_dates():
            for row in self._iter_events(file_date):
                if row[_QUADCLASS] != _QUAD_MATERIAL_CONFLICT:
                    continue
                iso3 = wanted_fips.get(row[_ACTIONGEO_CC])
                if iso3 is None:
                    continue
                n = _to_int(row[_NUM_ARTICLES])
                bucket = agg.get(iso3)
                if bucket is None:
                    bucket = agg[iso3] = {"articles": 0, "best": -1, "root": "", "url": "", "date": None}
                bucket["articles"] += n
                if n > bucket["best"]:
                    bucket["best"] = n
                    bucket["root"] = row[_EVENT_ROOT]
                    bucket["url"] = row[_SOURCEURL]
                    bucket["date"] = _parse_date(row[_DATEADDED]) or _parse_date(row[_SQLDATE])
        return {iso3: b for iso3, b in agg.items() if b["articles"] >= self.min_articles}

    def _iter_events(self, file_date: dt.date) -> Iterator[list[str]]:
        """Stream the rows of one daily export; a missing/unreachable day is skipped."""
        url = f"{self.base_url}/{file_date:%Y%m%d}.export.CSV.zip"
        try:
            response = _session().get(url, headers={"User-Agent": USER_AGENT}, timeout=self.timeout)
            response.raise_for_status()
        except requests.RequestException:
            return  # not yet published, gap, or transient network error → skip
        try:
            archive = zipfile.ZipFile(io.BytesIO(response.content))
            name = archive.namelist()[0]
        except (zipfile.BadZipFile, IndexError):
            return
        with archive.open(name) as handle:
            reader = csv.reader(io.TextIOWrapper(handle, encoding="utf-8", errors="replace"), delimiter="\t")
            for row in reader:
                if len(row) >= _MIN_FIELDS:
                    yield row

    def _recent_dates(self) -> list[dt.date]:
        # Start at yesterday: today's daily file is published after the day ends.
        today = dt.date.today()
        return [today - dt.timedelta(days=offset) for offset in range(1, self.lookback_days + 1)]
