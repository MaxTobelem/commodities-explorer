"""API tests: auth, the combined instrument catalogue, and the /backtest endpoint."""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from commodities.models import Commodity
from markets.models import AssetPrice, MarketAsset
from markets.services import month_end

pytestmark = pytest.mark.django_db

A = MarketAsset.AssetClass


def client():
    user = get_user_model().objects.create_user("a", "a@e.com", "x")
    c = APIClient()
    c.force_authenticate(user)
    return c


def gen_months(start, n):
    out, (y, m) = [], start
    for _ in range(n):
        out.append((y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def mk_asset(code, asset_class, currency, series):
    a = MarketAsset.objects.create(code=code, name=code, asset_class=asset_class, currency=currency)
    AssetPrice.objects.bulk_create(
        [AssetPrice(asset=a, date=month_end(ym), value=Decimal(str(v))) for ym, v in series.items()]
    )
    return a


def seed(months):
    mk_asset("SBWMUD1L", A.CASH, "USD", {m: 100 + i for i, m in enumerate(months)})
    mk_asset("USCPI", A.CPI, "USD", {m: 100 + 0.5 * i for i, m in enumerate(months)})
    mk_asset("EURBGN", A.FX, "USD", {m: 1.2 for m in months})
    mk_asset("STOCK", A.EQUITY, "USD", {m: 100 * (1.01**i) for i, m in enumerate(months)})
    mk_asset("BONDX", A.BOND, "USD", {m: 100 * (1.002**i) for i, m in enumerate(months)})


def test_requires_authentication():
    assert APIClient().get("/api/market-assets/instruments/").status_code in (401, 403)
    assert APIClient().post("/api/backtest/", {}, format="json").status_code in (401, 403)


def test_instruments_lists_assets_and_commodities():
    seed(gen_months((2020, 1), 3))
    Commodity.objects.create(name="Or", slug="gold")
    items = client().get("/api/market-assets/instruments/").json()
    refs = {i["ref"] for i in items}
    assert "asset:STOCK" in refs and "commodity:gold" in refs
    # CPI/FX/cash-internal series are never offered as allocatable instruments.
    assert "asset:USCPI" not in refs and "asset:EURBGN" not in refs


def test_instruments_search_filter():
    seed(gen_months((2020, 1), 3))
    items = client().get("/api/market-assets/instruments/?q=bond").json()
    assert items and all("bond" in i["label"].lower() or "bond" in i["ref"].lower() for i in items)


def test_backtest_endpoint_happy_path():
    seed(gen_months((2018, 1), 36))
    body = {
        "amount": 1000,
        "currency": "USD",
        "rebalance": "monthly",
        "fee_percent": 0.2,
        "allocations": [{"name": "60/40", "weights": {"asset:STOCK": 60, "asset:BONDX": 40}}],
        "benchmark": {"name": "Actions", "weights": {"asset:STOCK": 100}},
    }
    r = client().post("/api/backtest/", body, format="json")
    assert r.status_code == 200
    data = r.json()
    assert len(data["dates"]) == 36
    res = data["results"][0]
    assert len(res["equity_net"]) == 36
    assert res["metrics"]["final_net"] <= res["metrics"]["final_gross"]
    assert res["relative"]["tracking_error"] is not None
    assert data["benchmark"]["relative"] is None


def test_backtest_rejects_empty_allocations():
    seed(gen_months((2020, 1), 12))
    r = client().post("/api/backtest/", {"allocations": []}, format="json")
    assert r.status_code == 400


def test_backtest_rejects_unknown_instrument():
    seed(gen_months((2020, 1), 12))
    body = {"currency": "USD", "allocations": [{"name": "x", "weights": {"asset:NOPE": 100}}]}
    r = client().post("/api/backtest/", body, format="json")
    assert r.status_code == 400
