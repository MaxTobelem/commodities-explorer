"""Shared heuristics for the French commodity *news* providers (gnews, presse).

Both turn real headlines into events, so they share the same small French
lexicons to read a price **direction** and an event **category** from a headline,
and to gate out off-topic noise. Pure (stdlib + requests), no DB side effects.
"""

from __future__ import annotations

import datetime as dt
import html
import re
from email.utils import parsedate_to_datetime

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from commodities.models import Event, EventImpact

USER_AGENT = "Mozilla/5.0 (compatible; commodities-explorer/1.0; research dashboard)"

# Direction lexicon — substring match on the normalized headline.
UP = (
    "hausse",
    "flamb",
    "grimp",
    "bondit",
    "envol",
    "augment",
    "record",
    "plus haut",
    "sommet",
    "pénurie",
    "penurie",
    "rupture",
    "embargo",
    "sanction",
    "grève",
    "greve",
    "sécheresse",
    "secheresse",
    "inondation",
    "déficit",
    "deficit",
    "choc",
    "tension",
    "perturbation",
    "blocage",
    "restriction",
    "s'envole",
    "dopé",
    "dope",
    "rebond",
    "rebondit",
    "se redresse",
    "redress",
    "renchéri",
    "renchérit",
)
DOWN = (
    "baisse",
    "recul",
    "chut",
    "effondr",
    "plus bas",
    "surplus",
    "excédent",
    "excedent",
    "surproduction",
    "abondante",
    "repli",
    "détend",
    "detend",
    "se tasse",
    "plonge",
    "dégringol",
    "retombe",
    "corrige",
    "correction",
    "céder",
    "cède",
    "fléchit",
    "flechit",
    "allège",
    "allege",
)

# Category lexicons (priority order: war > disaster > policy > else economic).
CAT_WAR = (
    "guerre",
    "conflit",
    "attaque",
    "frappe",
    "militaire",
    "missile",
    "drone",
    "bombard",
    "offensive",
    "belligér",
    "belliger",
    "troupes",
    "combats",
)
CAT_DISASTER = (
    "sécheresse",
    "secheresse",
    "inondation",
    "gelée",
    "gelee",
    "ouragan",
    "cyclone",
    "séisme",
    "seisme",
    "tremblement",
    "incendie",
    "tempête",
    "tempete",
    "canicule",
    "catastrophe",
    "épidémie",
    "epidemie",
    "ravageur",
)
CAT_POLICY = (
    "tarif",
    "douane",
    "taxe",
    "sanction",
    "embargo",
    "quota",
    "interdiction",
    "interdit",
    "régulation",
    "regulation",
    "nationalis",
    "subvention",
    "ministre",
    "gouvernement",
    "élection",
    "election",
    "accord",
    "réglementation",
    "reglementation",
)
# A headline must carry at least one market/event signal to be kept — drops the
# off-topic noise (agronomy how-tos, gadgets, animal-health…) that merely names a
# commodity. Includes exchange/market vocabulary (Euronext, Chicago, USDA…).
MARKET = (
    "cours",
    "prix",
    "marché",
    "marche",
    "production",
    "récolte",
    "recolte",
    "export",
    "import",
    "pénurie",
    "penurie",
    "offre",
    "demande",
    "stock",
    "tonne",
    "baril",
    "once",
    "lme",
    "fonderie",
    "mine",
    "raffin",
    "gisement",
    "extraction",
    "approvisionnement",
    "filière",
    "filiere",
    "opep",
    "flamb",
    "grimp",
    "recul",
    "chut",
    "hausse",
    "baisse",
    "euronext",
    "chicago",
    "cbot",
    "usda",
    "€/t",
    "$/t",
    "dollar",
    "rebond",
    "retombe",
    "corrige",
    "consolid",
    "stabilis",
    "cotation",
    "contrat",
    "négoci",
    "negoci",
)
RELEVANT = (*MARKET, *CAT_WAR, *CAT_DISASTER, *CAT_POLICY)

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def make_session() -> requests.Session:
    """A requests session that retries transient 5xx on GET (for flaky feeds)."""
    retry = Retry(
        total=2,
        connect=2,
        backoff_factor=1.0,
        status_forcelist=(500, 502, 503, 504),
        allowed_methods=frozenset({"GET"}),
    )
    session = requests.Session()
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def clean_html(text: str) -> str:
    """Strip tags, unescape entities (incl. &nbsp;), collapse whitespace."""
    return _WS.sub(" ", html.unescape(_TAG.sub(" ", text or ""))).strip()


def normalize(text: str) -> str:
    """Lowercase and fold typographic apostrophes — for keyword matching."""
    return text.replace("’", "'").replace("ʼ", "'").lower()


def parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    try:
        return parsedate_to_datetime(raw).date()
    except (TypeError, ValueError):
        return None


def score_direction(norm_text: str, up: tuple[str, ...], down: tuple[str, ...]) -> str:
    """UP/DOWN/NEUTRAL by counting lexicon hits in already-normalized text.

    Takes the lexicons as arguments so an English news source can reuse it with
    its own word lists (see datasources/mining.py)."""
    n_up = sum(1 for w in up if w in norm_text)
    n_down = sum(1 for w in down if w in norm_text)
    if n_up > n_down:
        return EventImpact.Direction.UP
    if n_down > n_up:
        return EventImpact.Direction.DOWN
    return EventImpact.Direction.NEUTRAL


def classify(
    norm_text: str, war: tuple[str, ...], disaster: tuple[str, ...], policy: tuple[str, ...]
) -> str:
    """Event category by priority: war > disaster > policy > else economic."""
    if any(w in norm_text for w in war):
        return Event.Type.WAR
    if any(w in norm_text for w in disaster):
        return Event.Type.DISASTER
    if any(w in norm_text for w in policy):
        return Event.Type.POLICY
    return Event.Type.ECONOMIC


def direction(text: str) -> str:
    return score_direction(normalize(text), UP, DOWN)


def categorize(text: str) -> str:
    return classify(normalize(text), CAT_WAR, CAT_DISASTER, CAT_POLICY)


def is_relevant(text: str) -> bool:
    """True if the (head)line carries a market/war/disaster/policy signal."""
    return any(w in normalize(text) for w in RELEVANT)


def summarize(raw_desc: str, publisher: str, fallback: str, *, max_len: int = 500) -> str:
    """Real feed chapô (cleaned, trimmed) + ' — publisher'; `fallback` if too short."""
    desc = clean_html(raw_desc)
    if len(desc) < 40:
        return fallback
    if len(desc) > max_len:
        desc = desc[:max_len].rsplit(" ", 1)[0] + "…"
    return f"{desc} — {publisher}"
