"""Commodity news for **metals** — curated English mining feeds, with real summaries.

The French publisher feeds (presse.py) cover energy + agriculture well but not
metals, and no fresh *French* feed with real summaries does (Agence Ecofin is
frozen, Commodafrica 503s). The reputable English mining press does — so, for
metals only, this provider mirrors presse against English feeds (Mining.com, The
Northern Miner): real headline + real summary, matched to our metal commodities
by English keywords, with direction/category from small English lexicons.

Matching/scoring run on the **English** text (the lexicons are English); the
displayed title + summary are then **translated to French** (deep-translator, free,
with graceful English fallback) so the dashboard stays in French.

Same strictness as presse: the metal term must be in the **title** and the title
must carry a market/event signal. refresh_events runs this as a second primary
(after presse); Google News still fills whatever neither covers.
"""

from __future__ import annotations

import datetime as dt
import re
from typing import TYPE_CHECKING
from xml.etree import ElementTree as ET

import requests
from django.conf import settings

from .base import EnrichmentProvider, EnrichmentResult, ImpactRecord
from .newslex import (
    USER_AGENT,
    classify,
    clean_html,
    make_session,
    normalize,
    parse_date,
    score_direction,
)

if TYPE_CHECKING:
    from commodities.models import Commodity

# (publisher label, feed URL) — fresh English mining feeds with real summaries
# (validated live). Metals/precious only.
FEEDS: tuple[tuple[str, str], ...] = (
    ("Mining.com", "https://www.mining.com/feed/"),
    ("The Northern Miner", "https://www.northernminer.com/feed/"),
)

# English lexicons — substring match on normalized text. Terms are chosen to be
# distinctive enough as substrings to avoid collisions (no bare "war"→warehouse,
# "ban"→bank, "gain"→against, "ore"→more…).
_UP = (
    "rally",
    "surge",
    "soar",
    "jump",
    "climb",
    "rebound",
    "spike",
    "higher",
    "record high",
    "shortage",
    "deficit",
    "disruption",
    "squeeze",
    "boom",
    "strengthen",
    "sanction",
    "tariff",
    "embargo",
    "strike",
    "halt",
)
_DOWN = (
    "fall",
    "drop",
    "slump",
    "decline",
    "plunge",
    "tumble",
    "weaken",
    "glut",
    "surplus",
    "oversupply",
    "retreat",
    "sink",
    "downturn",
    "pullback",
    "selloff",
    "slips",
    "softer",
    "lower",
)
_MARKET = (
    "price",
    "supply",
    "demand",
    "output",
    "production",
    "mining",
    "miner",
    "smelter",
    "refinery",
    "tonne",
    "ounce",
    "futures",
    "stockpile",
    "inventory",
    "export",
    "import",
    "deficit",
    "surplus",
    "forecast",
    "deposit",
    "reserves",
    "concentrate",
    "market",
    "comex",
    " lme ",
    "quota",
    "royalty",
    "$",
)
_WAR = ("conflict", "military", "missile", "invasion", "troops", "airstrike", "frontline")
_DISASTER = (
    "drought",
    "flood",
    "hurricane",
    "cyclone",
    "earthquake",
    "wildfire",
    "landslide",
    "storm",
    "tailings",
)
_POLICY = (
    "tariff",
    "sanction",
    "quota",
    "embargo",
    "royalty",
    "nationaliz",
    "nationalis",
    "subsidy",
    "regulation",
    "permit",
    "ministry",
    "government",
    "election",
    "duties",
    "export ban",
    "import ban",
    "strike",
)
_RELEVANT = (*_MARKET, *_WAR, *_DISASTER, *_POLICY)

# slug → English patterns, matched on the normalized **title**. Metals only.
_PATTERNS: dict[str, re.Pattern[str]] = {
    "aluminium": r"\balumini?um\b|\balumina\b|\bbauxite\b",
    "cuivre": r"\bcopper\b",
    "minerai-de-fer": r"\biron ore\b",
    "plomb": (
        r"lead and zinc|zinc and lead|lead price|lead ore|lead smelter|"
        r"lead mine|refined lead|lead concentrate"
    ),
    "etain": r"\btin\b",
    "nickel": r"\bnickel\b",
    "zinc": r"\bzinc\b",
    "or": r"\bgold\b",
    "platine": r"\bplatinum\b",
    "argent": r"\bsilver\b",
    "cobalt": r"\bcobalt\b",
}
_PATTERNS = {slug: re.compile(p, re.IGNORECASE) for slug, p in _PATTERNS.items()}
_EXCLUDES: dict[str, tuple[str, ...]] = {
    "or": ("gold coast", "gold medal", "goldman"),
    "argent": ("silver lining", "silver screen", "silverware"),
    "etain": ("tin can",),
}


_MAX_SUMMARY = 500


def _match_slugs(norm_title: str) -> list[str]:
    return [
        slug
        for slug, pat in _PATTERNS.items()
        if pat.search(norm_title) and not any(x in norm_title for x in _EXCLUDES.get(slug, ()))
    ]


def _chapo(raw_desc: str) -> str:
    """Cleaned, trimmed article summary (no attribution); '' if too short."""
    desc = clean_html(raw_desc)
    if len(desc) < 40:
        return ""
    if len(desc) > _MAX_SUMMARY:
        desc = desc[:_MAX_SUMMARY].rsplit(" ", 1)[0] + "…"
    return desc


def _translate_fr(texts: list[str]) -> dict[str, str]:
    """English → French for a batch of strings, returned as an {en: fr} map.

    Uses deep-translator's free Google endpoint (no key). On any failure returns
    an empty map so callers keep the original English — a translation outage
    degrades to English text, it never drops or aborts the news refresh.
    """
    try:
        from deep_translator import GoogleTranslator

        out = GoogleTranslator(source="en", target="fr").translate_batch(texts)
    except Exception:  # noqa: BLE001 — network/library hiccup → fall back to English
        return {}
    return {en: (fr or en) for en, fr in zip(texts, out)}


class MiningNewsProvider(EnrichmentProvider):
    key = "mining"

    @property
    def feeds(self) -> tuple[tuple[str, str], ...]:
        return getattr(settings, "MINING_FEEDS", FEEDS)

    @property
    def max_per_commodity(self) -> int:
        return getattr(settings, "MINING_MAX_PER_COMMODITY", 4)

    @property
    def lookback_days(self) -> int:
        return getattr(settings, "MINING_LOOKBACK_DAYS", 14)

    @property
    def timeout(self) -> int:
        return getattr(settings, "MINING_TIMEOUT", 20)

    @property
    def translate(self) -> bool:
        return getattr(settings, "MINING_TRANSLATE", True)

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        result = EnrichmentResult()
        wanted = {c.slug: c for c in commodities if c.slug in _PATTERNS}
        if not wanted:
            return result
        cutoff = dt.date.today() - dt.timedelta(days=self.lookback_days)
        session = make_session()

        candidates: dict[str, list[dict]] = {}
        for publisher, url in self.feeds:
            try:
                items = self._fetch_items(session, url)
            except (requests.RequestException, ET.ParseError):
                continue  # isolate per-feed failures — never abort the run
            for item in items:
                title = clean_html(item.findtext("title") or "")
                link = (item.findtext("link") or "").strip()
                date = parse_date(item.findtext("pubDate"))
                if not title or not link or date is None or date < cutoff:
                    continue
                norm_title = normalize(title)
                if not any(w in norm_title for w in _RELEVANT):
                    continue  # metal named but no market/event signal → skip
                slugs = [s for s in _match_slugs(norm_title) if s in wanted]
                if not slugs:
                    continue
                desc = item.findtext("description") or ""
                for slug in slugs:
                    candidates.setdefault(slug, []).append(
                        {"date": date, "title": title, "desc": desc, "link": link, "pub": publisher}
                    )

        # Pick per commodity (cap + dedup), scoring on the *English* text.
        picked: list[dict] = []
        for slug, cands in candidates.items():
            cands.sort(key=lambda c: c["date"], reverse=True)
            seen_titles: set[str] = set()
            n = 0
            for c in cands:
                if n >= self.max_per_commodity:
                    break
                title_key = normalize(c["title"])
                if title_key in seen_titles:
                    continue
                seen_titles.add(title_key)
                blob = normalize(f"{c['title']} {clean_html(c['desc'])}")
                picked.append(
                    {
                        "commodity": wanted[slug],
                        "title": c["title"][:190],
                        "chapo": _chapo(c["desc"]),
                        "date": c["date"],
                        "link": c["link"],
                        "pub": c["pub"],
                        "type": classify(blob, _WAR, _DISASTER, _POLICY),
                        "direction": score_direction(blob, _UP, _DOWN),
                    }
                )
                n += 1

        # Translate the displayed strings (title + chapô) EN→FR in one batch.
        translations: dict[str, str] = {}
        if self.translate:
            texts = sorted(
                {r["title"] for r in picked} | {r["chapo"] for r in picked if r["chapo"]}
            )
            if texts:
                translations = _translate_fr(texts)

        for r in picked:
            title = translations.get(r["title"], r["title"])[:190]
            chapo = translations.get(r["chapo"], r["chapo"]) if r["chapo"] else ""
            description = f"{chapo} — {r['pub']}" if chapo else f"Source : {r['pub']}."
            result.impacts.append(
                ImpactRecord(
                    commodity=r["commodity"],
                    event_title=title,
                    event_type=r["type"],
                    start_date=r["date"],
                    description=description,
                    source_url=r["link"],
                    direction=r["direction"],
                    magnitude=None,
                    source=self.key,
                )
            )
        return result

    # -- internals -----------------------------------------------------------

    def _fetch_items(self, session: requests.Session, url: str) -> list[ET.Element]:
        response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=self.timeout)
        response.raise_for_status()
        return ET.fromstring(response.content).findall(".//item")
