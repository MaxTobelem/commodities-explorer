"""Portfolio valuation & rules — everything is replayed from the Transaction
journal (the single source of truth), so back-dating and "as-of date" valuation
are trivial and always consistent.

A portfolio is **mono-currency**: every amount, price, fee and P&L is expressed in
its ``base_currency`` (EUR or USD). Commodity prices come from ``PriceQuote`` in the
matching column (``price_eur``/``price_usd``), with an FX fallback when the native
column is missing.
"""

from __future__ import annotations

import bisect
import datetime as dt
from dataclasses import dataclass, field
from decimal import Decimal

from django.conf import settings

from commodities.api.views import prefer_daily_in_overlap
from commodities.models import Commodity, PriceQuote

from .models import Portfolio, Transaction

# Quantities can be tiny fractions (e.g. €1000 of gold) — compare with a tolerance.
QTY_EPS = Decimal("0.00000001")
ZERO = Decimal("0")


class PortfolioError(Exception):
    """A business-rule violation (no price on date, oversell, insufficient cash…).
    Surfaced as HTTP 400 by the API layer."""


def eur_usd_rate() -> Decimal:
    """EUR per 1 USD (approximate, configurable). price_eur ≈ price_usd * rate."""
    return Decimal(str(getattr(settings, "EUR_USD_RATE", "0.92")))


def _quote_in_currency(quote: PriceQuote, currency: str) -> Decimal:
    """Price of one quote in the requested currency, FX-converting if the native
    column is missing."""
    rate = eur_usd_rate()
    if currency == Portfolio.Currency.EUR:
        if quote.price_eur is not None:
            return quote.price_eur
        return quote.price_usd * rate
    # USD
    if quote.price_usd is not None:
        return quote.price_usd
    return quote.price_eur / rate


def compute_fee(portfolio: Portfolio, amount: Decimal) -> Decimal:
    """Broker fee on a trade of ``amount`` (portfolio currency)."""
    pct = portfolio.fee_percent / Decimal("100")
    return (amount * pct + portfolio.fee_fixed).quantize(Decimal("0.01"))


def price_at(commodity: Commodity, date: dt.date, currency: str) -> Decimal | None:
    """Latest price on/before ``date`` (carry-forward), daily source preferred,
    in ``currency``. None if no quote exists on/before that date."""
    quotes = list(commodity.prices.filter(date__lte=date))
    if not quotes:
        return None
    quotes = prefer_daily_in_overlap(quotes)
    quotes.sort(key=lambda q: q.date)
    return _quote_in_currency(quotes[-1], currency)


# --- Ledger replay ----------------------------------------------------------


@dataclass
class _Position:
    qty: Decimal = ZERO
    cost: Decimal = ZERO  # total cost basis (incl. buy fees), portfolio currency


@dataclass
class _State:
    cash: Decimal = ZERO
    net_deposits: Decimal = ZERO
    realized_pnl: Decimal = ZERO
    fees_total: Decimal = ZERO
    positions: dict[int, _Position] = field(default_factory=dict)


def _replay(transactions: list[Transaction], *, validate: bool = False) -> _State:
    """Fold the (chronologically ordered) journal into a running state. With
    ``validate=True`` it enforces the business rules (used when adding a txn);
    for valuation of already-saved data it trusts the journal."""
    st = _State()
    for t in transactions:
        fee = t.fee or ZERO
        if t.kind == Transaction.Kind.DEPOSIT:
            st.cash += t.amount - fee
            st.net_deposits += t.amount
        elif t.kind == Transaction.Kind.WITHDRAW:
            if validate and st.cash < t.amount + fee:
                raise PortfolioError("Retrait supérieur à la trésorerie disponible.")
            st.cash -= t.amount + fee
            st.net_deposits -= t.amount
        elif t.kind == Transaction.Kind.BUY:
            if validate and st.cash < t.amount + fee:
                raise PortfolioError(
                    "Trésorerie insuffisante pour cet achat — déposez d'abord des fonds."
                )
            st.cash -= t.amount + fee
            pos = st.positions.setdefault(t.commodity_id, _Position())
            pos.qty += t.quantity
            pos.cost += t.amount + fee
        elif t.kind == Transaction.Kind.SELL:
            pos = st.positions.get(t.commodity_id)
            if validate and (pos is None or pos.qty < t.quantity - QTY_EPS):
                raise PortfolioError("Vente supérieure à la quantité détenue (pas de vente à découvert).")
            if pos is None:  # tolerate during non-validating replay
                pos = st.positions.setdefault(t.commodity_id, _Position())
            cost_portion = (pos.cost * (t.quantity / pos.qty)) if pos.qty > ZERO else ZERO
            proceeds = t.amount - fee
            st.cash += proceeds
            st.realized_pnl += proceeds - cost_portion
            pos.qty -= t.quantity
            pos.cost -= cost_portion
            if pos.qty <= QTY_EPS:
                pos.qty = ZERO
                pos.cost = ZERO
        st.fees_total += fee
    return st


def _ordered(transactions: list[Transaction]) -> list[Transaction]:
    # Same order as Meta.ordering (date, id); a not-yet-saved txn (id None) sorts last.
    return sorted(transactions, key=lambda t: (t.date, t.id or 10**18))


def prepare_transaction(
    portfolio: Portfolio,
    *,
    kind: str,
    date: dt.date,
    commodity: Commodity | None = None,
    amount: Decimal | None = None,
    quantity: Decimal | None = None,
    note: str = "",
) -> Transaction:
    """Build (but do not save) a validated Transaction with its price/quantity/fee
    snapshotted. Validates the **whole** resulting timeline (back-dating included)
    so the portfolio can never reach a negative cash or oversold state."""
    if kind in (Transaction.Kind.DEPOSIT, Transaction.Kind.WITHDRAW):
        if amount is None or amount <= ZERO:
            raise PortfolioError("Montant requis (> 0).")
        txn = Transaction(
            portfolio=portfolio, date=date, kind=kind, amount=amount,
            fee=ZERO, note=note,
        )
    elif kind in (Transaction.Kind.BUY, Transaction.Kind.SELL):
        if commodity is None:
            raise PortfolioError("Matière requise pour un achat/vente.")
        price = price_at(commodity, date, portfolio.base_currency)
        if price is None or price <= ZERO:
            raise PortfolioError(f"Pas de cours pour {commodity.name} au {date:%d/%m/%Y}.")
        if amount is not None and quantity is None:
            quantity = (amount / price)
        elif quantity is not None and amount is None:
            amount = (quantity * price).quantize(Decimal("0.01"))
        else:
            raise PortfolioError("Fournir soit un montant, soit une quantité (pas les deux).")
        if amount <= ZERO or quantity <= ZERO:
            raise PortfolioError("Montant/quantité doivent être positifs.")
        fee = compute_fee(portfolio, amount)
        txn = Transaction(
            portfolio=portfolio, date=date, kind=kind, commodity=commodity,
            amount=amount, quantity=quantity, unit_price=price, fee=fee, note=note,
        )
    else:
        raise PortfolioError(f"Type de transaction inconnu : {kind}.")

    # Validate the full prospective timeline.
    timeline = _ordered(list(portfolio.transactions.all()) + [txn])
    _replay(timeline, validate=True)
    return txn


# --- Valuation --------------------------------------------------------------


def value_portfolio(portfolio: Portfolio, as_of: dt.date | None = None) -> dict:
    """Snapshot of the portfolio at ``as_of`` (default = today): cash, positions
    valued at carry-forward prices, and clearly-separated P&L."""
    as_of = as_of or dt.date.today()
    currency = portfolio.base_currency
    txns = list(portfolio.transactions.filter(date__lte=as_of))
    st = _replay(_ordered(txns))

    commodities = {c.id: c for c in Commodity.objects.filter(id__in=st.positions.keys())}
    positions = []
    positions_value = ZERO
    for cid, pos in st.positions.items():
        if pos.qty <= ZERO:
            continue
        commodity = commodities[cid]
        price = price_at(commodity, as_of, currency)
        if price is None:
            continue
        market_value = pos.qty * price
        positions_value += market_value
        avg_cost = pos.cost / pos.qty if pos.qty else ZERO
        positions.append(
            {
                "commodity": commodity,
                "quantity": pos.qty,
                "avg_cost": avg_cost,
                "price": price,
                "cost_basis": pos.cost,
                "market_value": market_value,
                "unrealized_pnl": market_value - pos.cost,
            }
        )

    for p in positions:  # weights once the total is known
        p["weight"] = (p["market_value"] / positions_value * 100) if positions_value else ZERO

    total_value = st.cash + positions_value
    total_pnl = total_value - st.net_deposits
    invested = sum((p["cost_basis"] for p in positions), ZERO)
    return {
        "as_of": as_of,
        "currency": currency,
        "cash": st.cash,
        "invested": invested,
        "positions_value": positions_value,
        "total_value": total_value,
        "net_deposits": st.net_deposits,
        "realized_pnl": st.realized_pnl,
        "unrealized_pnl": positions_value - invested,
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / st.net_deposits * 100) if st.net_deposits > ZERO else ZERO,
        "fees_total": st.fees_total,
        "positions": sorted(positions, key=lambda p: p["market_value"], reverse=True),
    }


# --- Value history (time series) -------------------------------------------


def _price_lookup(commodity: Commodity, currency: str) -> tuple[list[dt.date], list[Decimal]]:
    """Sorted (dates, prices-in-currency) for fast carry-forward bisect."""
    quotes = prefer_daily_in_overlap(list(commodity.prices.all()))
    quotes.sort(key=lambda q: q.date)
    return [q.date for q in quotes], [_quote_in_currency(q, currency) for q in quotes]


def _carry_forward(dates: list[dt.date], prices: list[Decimal], on: dt.date) -> Decimal | None:
    i = bisect.bisect_right(dates, on) - 1
    return prices[i] if i >= 0 else None


def _axis(start: dt.date, end: dt.date, resolution: str) -> list[dt.date]:
    step = {"daily": 1, "weekly": 7}.get(resolution, 0)
    if step:
        out, d = [], start
        while d <= end:
            out.append(d)
            d += dt.timedelta(days=step)
        if out[-1] != end:
            out.append(end)
        return out
    # monthly: last day of each month in range + the end
    out, d = [], start
    while d <= end:
        out.append(d)
        d = (d.replace(day=1) + dt.timedelta(days=32)).replace(day=1)
    if out[-1] != end:
        out.append(end)
    return out


def history(
    portfolio: Portfolio,
    start: dt.date | None = None,
    end: dt.date | None = None,
    resolution: str = "daily",
) -> list[dict]:
    """Value (+ invested & cash) over time. Loads each held commodity's price
    series once and forward-fills along a date axis (no per-date DB hit)."""
    currency = portfolio.base_currency
    txns = _ordered(list(portfolio.transactions.all()))
    if not txns:
        return []
    end = end or dt.date.today()
    start = start or txns[0].date
    if start > end:
        return []

    lookups = {
        cid: _price_lookup(c, currency)
        for cid, c in {
            t.commodity_id: t.commodity for t in txns if t.commodity_id
        }.items()
    }

    points = []
    for d in _axis(start, end, resolution):
        st = _replay([t for t in txns if t.date <= d])
        positions_value = ZERO
        for cid, pos in st.positions.items():
            if pos.qty <= ZERO:
                continue
            dates, prices = lookups[cid]
            price = _carry_forward(dates, prices, d)
            if price is not None:
                positions_value += pos.qty * price
        invested = sum((p.cost for p in st.positions.values()), ZERO)
        points.append(
            {
                "date": d,
                "value": st.cash + positions_value,
                "invested": invested,
                "cash": st.cash,
            }
        )
    return points
