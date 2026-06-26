import datetime as dt

from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from commodities.models import Commodity
from markets import backtest as bt
from markets.catalog import INVESTABLE_CLASSES
from markets.models import MarketAsset
from markets.services import MarketError

from .serializers import MarketAssetSerializer


def _date(value):
    if not value:
        return None
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise MarketError(f"Date invalide : {value}.") from exc


def _float(value, default=None):
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise MarketError(f"Nombre invalide : {value}.") from exc


def _instruments() -> list[dict]:
    """The combined, allocatable universe: imported indices + physical commodities."""
    out: list[dict] = []
    for a in MarketAsset.objects.filter(asset_class__in=INVESTABLE_CLASSES):
        out.append(
            {
                "ref": f"asset:{a.code}",
                "label": a.name,
                "kind": "asset",
                "group": a.asset_class,
                "group_display": a.get_asset_class_display(),
                "currency": a.currency,
            }
        )
    for c in Commodity.objects.all().only("name", "slug", "category"):
        out.append(
            {
                "ref": f"commodity:{c.slug}",
                "label": c.name,
                "kind": "commodity",
                "group": c.category,
                "group_display": c.get_category_display(),
                "currency": "USD",
            }
        )
    out.sort(key=lambda i: (i["kind"] != "asset", i["group_display"], i["label"]))
    return out


class MarketAssetViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = MarketAsset.objects.all()
    serializer_class = MarketAssetSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["code", "name"]
    ordering = ["asset_class", "name"]
    pagination_class = None  # the whole (small) universe in one go

    @action(detail=False)
    def instruments(self, request):
        """Searchable list of every allocatable instrument (assets + commodities)."""
        items = _instruments()
        q = (request.query_params.get("q") or "").strip().lower()
        if q:
            items = [i for i in items if q in i["label"].lower() or q in i["ref"].lower()]
        return Response(items)


# --- Backtest ---------------------------------------------------------------


def _floats(arr, nd: int) -> list[float]:
    return [round(float(x), nd) for x in arr]


def _serialize_relative(rel: dict | None) -> dict | None:
    if rel is None:
        return None
    out = dict(rel)
    for key in ("best_relative_month", "worst_relative_month"):
        m = rel.get(key)
        if m:
            out[key] = {"value": round(m["value"], 6), "date": m["date"].isoformat()}
    out["tracking_error"] = round(rel["tracking_error"], 6)
    out["up_capture"] = round(rel["up_capture"], 1)
    out["down_capture"] = round(rel["down_capture"], 1)
    return out


def _serialize_result(r: dict) -> dict:
    m = r["metrics"]
    return {
        "name": r["name"],
        "weights": r["weights"],
        "equity_gross": _floats(r["equity_gross"], 2),
        "equity_net": _floats(r["equity_net"], 2),
        "drawdown": _floats(r["drawdown"], 6),
        "calendar_years": [{"year": y, "return": round(v, 6)} for y, v in r["calendar_years"]],
        "metrics": {
            "cagr": round(m["cagr"], 6),
            "annual_return": round(m["annual_return"], 6),
            "volatility": round(m["volatility"], 6),
            "sharpe": round(m["sharpe"], 4),
            "max_drawdown": round(m["max_drawdown"], 6),
            "inflation": round(m["inflation"], 6),
            "final_gross": round(m["final_gross"], 2),
            "final_net": round(m["final_net"], 2),
            "fees_total": round(m["fees_total"], 2),
            "var": {
                k: {"monthly": round(v["monthly"], 6), "annual": round(v["annual"], 6)}
                for k, v in m["var"].items()
            },
        },
        "relative": _serialize_relative(r["relative"]),
    }


def _parse_allocation(data: dict) -> bt.Allocation:
    name = (data.get("name") or "Allocation").strip()
    raw = data.get("weights") or {}
    if not isinstance(raw, dict) or not raw:
        raise MarketError(f"Allocation « {name} » sans pondérations.")
    weights = {str(ref): _float(w, 0) or 0 for ref, w in raw.items()}
    return bt.Allocation(name=name, weights=weights)


class BacktestView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        data = request.data
        try:
            allocations = [_parse_allocation(a) for a in (data.get("allocations") or [])]
            if not allocations:
                raise MarketError("Au moins une allocation est requise.")
            benchmark = _parse_allocation(data["benchmark"]) if data.get("benchmark") else None
            cfg = bt.BacktestConfig(
                start=_date(data.get("start")),
                end=_date(data.get("end")),
                amount=_float(data.get("amount"), 1000.0),
                currency=(data.get("currency") or "EUR").upper(),
                rebalance=(data.get("rebalance") or "monthly"),
                fee_percent=_float(data.get("fee_percent"), 0.20),
                benchmark=benchmark,
            )
            if cfg.currency not in ("EUR", "USD"):
                raise MarketError("Devise invalide (EUR ou USD).")
            res = bt.run_backtest(allocations, cfg)
        except MarketError as exc:
            return Response({"detail": str(exc)}, status=400)

        return Response(
            {
                "currency": res["currency"],
                "start": res["start"].isoformat(),
                "end": res["end"].isoformat(),
                "months": res["months"],
                "rebalance": res["rebalance"],
                "fee_percent": res["fee_percent"],
                "rf_cagr": round(res["rf_cagr"], 6),
                "inflation": round(res["inflation"], 6),
                "dates": [d.isoformat() for d in res["dates"]],
                "results": [_serialize_result(r) for r in res["results"]],
                "benchmark": _serialize_result(res["benchmark"]) if res["benchmark"] else None,
            }
        )
