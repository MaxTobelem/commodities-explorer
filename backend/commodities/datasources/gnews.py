"""Commodity news provider — real headlines from Google News RSS, per commodity.

We query Google News' RSS *search* in French for each commodity's market/supply
news and turn the most recent articles into events:
  - the **real headline** is the event title (explicit, not a heuristic label),
  - the publisher + date give context, the article is the source link,
  - the price **direction** and event **category** are read from small French
    lexicons (see newslex.py) — else *neutral*/*economic*, never fabricated.

Google News covers *every* commodity freshly, but its obfuscated redirect link
hides the article body, so events have no real description. The publisher-feed
provider (presse.py) is the primary source for the commodities it covers well;
refresh_events uses Google News to fill the rest (most metals, tropical softs).

Google News RSS is a public, unauthenticated feed (no key, no rate-limit for our
handful of daily requests); a per-commodity failure is isolated, never aborts the run.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

import requests
from django.conf import settings

from .base import EnrichmentProvider, EnrichmentResult, ImpactRecord
from .newslex import (
    USER_AGENT,
    categorize,
    clean_html,
    direction,
    is_relevant,
    make_session,
    parse_date,
)

if TYPE_CHECKING:
    from commodities.models import Commodity

GOOGLE_NEWS_RSS = "https://news.google.com/rss/search"

# Per-commodity French query (slug → query), focused on the *commodity market* to
# avoid consumer noise (coffee machines, lithium batteries) and the ambiguous
# words « or » (conjunction) and « argent » (money) — handled via quoted phrases.
_QUERIES: dict[str, str] = {
    # Énergie
    "petrole-brut-brent": "pétrole (Brent OR baril OR cours OR OPEP OR production)",
    "gaz-naturel-europe": '"gaz naturel" (Europe OR TTF OR cours OR prix OR approvisionnement)',
    "gaz-naturel-us": '"gaz naturel" ("États-Unis" OR "Henry Hub" OR cours OR production)',
    "gnl-japon": '(GNL OR "gaz naturel liquéfié") (cours OR prix OR Asie OR importations)',
    "charbon-australie": "charbon (thermique OR cours OR prix OR exportations OR production)",
    # Agricole — boissons
    "cacao": "cacao (cours OR prix OR récolte OR fèves OR production)",
    "cafe-arabica": "café (arabica OR robusta OR récolte OR cours OR producteurs)",
    "the": "thé (production OR récolte OR cours OR plantation OR exportations)",
    # Oléagineux
    "huile-de-palme": '"huile de palme" (cours OR prix OR production OR Indonésie OR Malaisie)',
    "soja": "soja (cours OR prix OR récolte OR production OR exportations)",
    "huile-de-soja": '"huile de soja" (cours OR prix OR production OR marché)',
    "huile-de-tournesol": '"huile de tournesol" (cours OR prix OR production OR marché)',
    # Céréales
    "ble-us-hrw": "blé (cours OR prix OR récolte OR exportations OR Euronext)",
    "mais": "maïs (cours OR prix OR récolte OR production OR exportations)",
    "riz": "riz (cours OR prix OR récolte OR exportations OR pénurie)",
    "orge": "orge (cours OR prix OR récolte OR production OR brassicole)",
    # Autres aliments
    "sucre-mondial": "sucre (cours OR prix OR canne OR betterave OR production)",
    "banane": "banane (cours OR prix OR production OR exportations OR récolte)",
    "boeuf": '(bœuf OR "viande bovine") (cours OR prix OR production OR exportations)',
    "crevettes": "crevettes (cours OR prix OR production OR élevage OR exportations)",
    # Matières premières agricoles
    "coton": "coton (cours OR prix OR récolte OR production OR exportations)",
    "caoutchouc": "caoutchouc (naturel OR hévéa OR cours OR prix OR production)",
    "bois-grumes": "bois (grumes OR sciage OR cours OR prix OR forêt)",
    "tabac": "tabac (production OR récolte OR feuilles OR cours OR exportations)",
    # Engrais
    "phosphate-roche": "phosphate (roche OR cours OR prix OR production OR engrais)",
    "dap-engrais": '"engrais phosphaté" (DAP OR cours OR prix OR marché)',
    "uree": "urée (engrais OR cours OR prix OR production OR azote)",
    "chlorure-de-potassium": '(potasse OR "chlorure de potassium") (cours OR prix OR engrais)',
    # Métaux de base
    "aluminium": "aluminium (cours OR prix OR production OR LME OR fonderie)",
    "cuivre": "cuivre (cours OR prix OR mine OR production OR LME)",
    "minerai-de-fer": '"minerai de fer" (cours OR prix OR production OR acier)',
    "plomb": "plomb (métal OR cours OR prix OR LME OR mine)",
    "etain": "étain (cours OR prix OR LME OR production OR mine)",
    "nickel": "nickel (cours OR prix OR LME OR production OR mine)",
    "zinc": "zinc (cours OR prix OR LME OR production OR mine)",
    # Métaux précieux (éviter « or »/« argent » ambigus → phrases entre guillemets)
    "or": '"cours de l\'or" OR "prix de l\'or" OR "once d\'or"',
    "platine": "platine (cours OR prix OR once OR production OR métal)",
    "argent": '"cours de l\'argent" OR "prix de l\'argent" OR "once d\'argent"',
    # Batterie
    "cobalt": "cobalt (cours OR prix OR mine OR RDC OR production OR raffinage)",
    # Élargissement Commodities-API (matières ajoutées en quotidien)
    "uranium": "uranium (cours OR prix OR nucléaire OR production OR enrichissement)",
    "petrole-brut-wti": "pétrole WTI (cours OR baril OR prix OR production)",
    "essence-rbob": "essence (prix OR carburant OR raffinerie OR cours)",
    "ethanol": "éthanol (cours OR prix OR biocarburant OR production)",
    "naphta": "naphta (cours OR prix OR pétrochimie OR raffinage)",
    "methanol": "méthanol (cours OR prix OR production OR pétrochimie)",
    "palladium": "palladium (cours OR prix OR once OR catalytique OR production)",
    "rhodium": "rhodium (cours OR prix OR once OR métal OR production)",
    "magnesium": "magnésium (cours OR prix OR production OR métal OR Chine)",
    "acier-hrc": "acier (cours OR prix OR sidérurgie OR production OR HRC)",
    "ferraille-d-acier": "ferraille (acier OR cours OR prix OR recyclage OR sidérurgie)",
    "colza": "colza (cours OR prix OR récolte OR production OR oléagineux)",
    "porc": '(porc OR "viande porcine") (cours OR prix OR production OR élevage)',
    "cafe-robusta": "café robusta (cours OR prix OR récolte OR production)",
    "avoine": "avoine (cours OR prix OR récolte OR production OR céréale)",
    "saumon": "saumon (cours OR prix OR élevage OR production OR Norvège)",
    "huile-de-coco": '"huile de coco" (cours OR prix OR production OR coprah)',
    "pvc": "PVC (cours OR prix OR production OR plastique OR résine)",
    "polypropylene": "polypropylène (cours OR prix OR production OR plastique)",
}

_MARKET_TERMS = "cours OR prix OR production OR récolte OR marché OR exportations"


def _clean_title(title: str, source: str) -> str:
    """Strip the ' - Publisher' suffix Google News appends to every headline."""
    title = clean_html(title)
    if source and title.endswith(f" - {source}"):
        return title[: -(len(source) + 3)].strip()
    head, sep, tail = title.rpartition(" - ")
    if sep and len(tail) <= 45:
        return head.strip()
    return title


class GoogleNewsProvider(EnrichmentProvider):
    key = "gnews"

    @property
    def base_url(self) -> str:
        return getattr(settings, "GNEWS_RSS_URL", GOOGLE_NEWS_RSS)

    @property
    def max_per_commodity(self) -> int:
        return getattr(settings, "GNEWS_MAX_PER_COMMODITY", 4)

    @property
    def lookback_days(self) -> int:
        return getattr(settings, "GNEWS_LOOKBACK_DAYS", 14)

    @property
    def timeout(self) -> int:
        return getattr(settings, "GNEWS_TIMEOUT", 20)

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        result = EnrichmentResult()
        cutoff = dt.date.today() - dt.timedelta(days=self.lookback_days)
        session = make_session()
        for commodity in commodities:
            try:
                items = self._fetch_items(session, self._query_for(commodity))
            except (requests.RequestException, ET.ParseError):
                continue  # isolate per-commodity failures — never abort the run
            candidates = []
            for item in items:
                title = clean_html(item.findtext("title") or "")
                link = (item.findtext("link") or "").strip()
                date = parse_date(item.findtext("pubDate"))
                if not title or not link or date is None or date < cutoff:
                    continue
                candidates.append((date, title, link, (item.findtext("source") or "").strip()))
            candidates.sort(key=lambda c: c[0], reverse=True)
            picked = 0
            seen_sources: set[str] = set()
            for date, title, link, source in candidates:
                if picked >= self.max_per_commodity:
                    break
                headline = _clean_title(title, source)
                if not is_relevant(headline):
                    continue  # drop off-topic noise that merely mentions the commodity
                key = source.lower()
                if key and key in seen_sources:  # 1 article per source → diversify the feed
                    continue
                seen_sources.add(key)
                result.impacts.append(
                    ImpactRecord(
                        commodity=commodity,
                        event_title=headline[:190],
                        event_type=categorize(headline),
                        start_date=date,
                        description=f"D'après {source}." if source else "",
                        source_url=link,
                        direction=direction(headline),
                        magnitude=None,
                        source=self.key,
                    )
                )
                picked += 1
        return result

    # -- internals -----------------------------------------------------------

    def _fetch_items(self, session: requests.Session, query: str) -> list[ET.Element]:
        params = {"q": query, "hl": "fr", "gl": "FR", "ceid": "FR:fr"}
        response = session.get(
            self.base_url, params=params, headers={"User-Agent": USER_AGENT}, timeout=self.timeout
        )
        response.raise_for_status()
        return ET.fromstring(response.content).findall(".//item")

    def _query_for(self, commodity: Commodity) -> str:
        query = _QUERIES.get(commodity.slug)
        if query:
            return query
        # Fallback: commodity name without parenthetical qualifiers + market terms.
        name = commodity.name.split("(")[0].strip()
        return f"{name} ({_MARKET_TERMS})"
