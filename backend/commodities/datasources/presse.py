"""Commodity news from curated French publisher RSS feeds — *with real summaries*.

Google News (gnews.py) gives fresh headlines for every commodity, but its
obfuscated redirect link hides the article, so events have no real description.
Direct publisher feeds are the opposite: narrower coverage, but each <item>
carries a genuine summary (chapô) we store as the event description.

So this is the **primary** news source for the commodities these feeds cover well
(energy + agriculture + fertilizers); refresh_events falls back to Google News for
the rest (most metals, tropical softs, niche goods).

Matching is deliberately strict to stay coherent: the commodity term must appear
in the **title** (not merely the body) *and* the title must carry a market/event
signal (newslex.is_relevant) — otherwise agronomy how-tos and off-topic mentions
leak in. Ambiguous words (or, argent, fer, bois, gaz) require a disambiguating
phrase, and word boundaries avoid substring traps (horizon→riz, théâtre→thé).
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
    categorize,
    clean_html,
    direction,
    is_relevant,
    make_session,
    normalize,
    parse_date,
)

if TYPE_CHECKING:
    from commodities.models import Commodity

# (publisher label, feed URL) — fresh French feeds whose <description> is a real
# summary (validated live). Energy + agriculture + fertilizers; metals & tropical
# softs are scarce in fresh FR RSS and left to the Google News fallback.
FEEDS: tuple[tuple[str, str], ...] = (
    ("Connaissance des Énergies", "https://www.connaissancedesenergies.org/rss.xml"),
    ("La France Agricole", "https://www.lafranceagricole.fr/rss"),
    ("Terre-net", "https://www.terre-net.fr/rss"),
    ("Web-agri", "https://www.web-agri.fr/rss"),
    ("Le Monde", "https://www.lemonde.fr/economie/rss_full.xml"),
    ("Le Figaro", "https://www.lefigaro.fr/rss/figaro_economie.xml"),
)

# slug → precise patterns, matched on the normalized **title**.
_PATTERNS: dict[str, re.Pattern[str]] = {
    "petrole-brut-brent": r"pétrol|\bbrent\b|\bbaril",
    "gaz-naturel-europe": (
        r"gaz naturel|gaz russe|gazier|\bttf\b|\bgnl\b|gaz liquéfié|"
        r"prix du gaz|cours du gaz|marché du gaz"
    ),
    "gaz-naturel-us": r"henry hub|gaz américain",
    "charbon-australie": r"\bcharbon",
    "cacao": r"\bcacao",
    "cafe-arabica": r"\bcafé|arabica|robusta",
    "the": r"thé noir|thé vert|marché du thé|cours du thé|production de thé|feuilles de thé",
    "huile-de-palme": r"huile de palme|palmier à huile",
    "soja": r"\bsoja",
    "huile-de-soja": r"huile de soja",
    "huile-de-tournesol": r"tournesol",
    "ble-us-hrw": r"\bblés?\b|blé tendre|blé dur|froment|céréal",
    "mais": r"\bmaïs\b",
    "riz": r"\briz\b",
    "orge": r"\borges?\b",
    "sucre-mondial": r"\bsucre|canne à sucre|betterave",
    "banane": r"\bbanane",
    "boeuf": r"bœuf|boeuf|viande bovine|\bbovin|filière bovine",
    "crevettes": r"crevette",
    "coton": r"\bcoton",
    "caoutchouc": r"caoutchouc|hévéa",
    "bois-grumes": (
        r"\bgrume|sciage|bois d'œuvre|bois d'oeuvre|bois rond|bois de construction|bois tropical"
    ),
    "tabac": r"\btabac",
    "phosphate-roche": r"phosphate",
    "dap-engrais": r"\bdap\b|\bengrais\b|fertilisant",
    "uree": r"\burée\b|\buree\b",
    "chlorure-de-potassium": r"potasse|chlorure de potassium|potassique",
    "aluminium": r"aluminium|alumine|bauxite",
    "cuivre": r"\bcuivre",
    "minerai-de-fer": r"minerai de fer|minerais de fer",
    "plomb": r"\bplomb",
    "etain": r"\bétain",
    "nickel": r"\bnickel",
    "zinc": r"\bzinc",
    "or": r"once[s]? d'or|cours de l'or|prix de l'or|marché de l'or|métal jaune|lingot",
    "platine": r"\bplatine",
    "argent": r"once[s]? d'argent|cours de l'argent|prix de l'argent|métal argent|argent métal",
    "cobalt": r"cobalt",
}
_PATTERNS = {slug: re.compile(p, re.IGNORECASE) for slug, p in _PATTERNS.items()}

# Substring excludes on the normalized title (false-positive killers).
_EXCLUDES: dict[str, tuple[str, ...]] = {
    "charbon-australie": ("charbon de bois", "charbon actif", "charbon végétal"),
    "plomb": ("sans plomb", "plomb dans", "plombémie", "saturnisme"),
}

_MIN_SUMMARY = 40  # shorter than this ⇒ no real chapô, fall back to attribution
_MAX_SUMMARY = 500


def _match_slugs(norm_title: str) -> list[str]:
    """Commodity slugs whose pattern matches the (normalized) title."""
    return [
        slug
        for slug, pat in _PATTERNS.items()
        if pat.search(norm_title) and not any(x in norm_title for x in _EXCLUDES.get(slug, ()))
    ]


def _summary(raw_desc: str, publisher: str) -> str:
    """The feed's real chapô (trimmed) + publisher attribution; fallback if empty."""
    desc = clean_html(raw_desc)
    if len(desc) < _MIN_SUMMARY:
        return f"D'après {publisher}."
    if len(desc) > _MAX_SUMMARY:
        desc = desc[:_MAX_SUMMARY].rsplit(" ", 1)[0] + "…"
    return f"{desc} — {publisher}"


class PresseProvider(EnrichmentProvider):
    key = "presse"

    @property
    def feeds(self) -> tuple[tuple[str, str], ...]:
        return getattr(settings, "PRESSE_FEEDS", FEEDS)

    @property
    def max_per_commodity(self) -> int:
        return getattr(settings, "PRESSE_MAX_PER_COMMODITY", 4)

    @property
    def lookback_days(self) -> int:
        return getattr(settings, "PRESSE_LOOKBACK_DAYS", 14)

    @property
    def timeout(self) -> int:
        return getattr(settings, "PRESSE_TIMEOUT", 20)

    def fetch(self, commodities: list[Commodity]) -> EnrichmentResult:
        result = EnrichmentResult()
        wanted = {c.slug: c for c in commodities if c.slug in _PATTERNS}
        if not wanted:
            return result
        cutoff = dt.date.today() - dt.timedelta(days=self.lookback_days)
        session = make_session()

        # slug → list of candidate articles (across all feeds), deduped/capped below.
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
                if not is_relevant(norm_title):
                    continue  # off-topic (agronomy how-to, gadget…) — no market signal
                slugs = [s for s in _match_slugs(norm_title) if s in wanted]
                if not slugs:
                    continue
                desc = item.findtext("description") or ""
                for slug in slugs:
                    candidates.setdefault(slug, []).append(
                        {"date": date, "title": title, "desc": desc, "link": link, "pub": publisher}
                    )

        for slug, cands in candidates.items():
            cands.sort(key=lambda c: c["date"], reverse=True)
            seen_titles: set[str] = set()
            picked = 0
            for c in cands:
                if picked >= self.max_per_commodity:
                    break
                title_key = normalize(c["title"])
                if title_key in seen_titles:  # same story across feeds → keep one
                    continue
                seen_titles.add(title_key)
                blob = f"{c['title']} {clean_html(c['desc'])}"  # title + body → richer signal
                result.impacts.append(
                    ImpactRecord(
                        commodity=wanted[slug],
                        event_title=c["title"][:190],
                        event_type=categorize(blob),
                        start_date=c["date"],
                        description=_summary(c["desc"], c["pub"]),
                        source_url=c["link"],
                        direction=direction(blob),
                        magnitude=None,
                        source=self.key,
                    )
                )
                picked += 1
        return result

    # -- internals -----------------------------------------------------------

    def _fetch_items(self, session: requests.Session, url: str) -> list[ET.Element]:
        response = session.get(url, headers={"User-Agent": USER_AGENT}, timeout=self.timeout)
        response.raise_for_status()
        return ET.fromstring(response.content).findall(".//item")
