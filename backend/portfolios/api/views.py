import datetime as dt
from decimal import Decimal, InvalidOperation

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from commodities.models import Commodity
from portfolios import services
from portfolios.models import Portfolio, Transaction

from . import serializers as s


def _date(value, default=None):
    if not value:
        return default
    try:
        return dt.date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise services.PortfolioError(f"Date invalide : {value}.") from exc


def _decimal(data, key):
    v = data.get(key)
    if v in (None, ""):
        return None
    try:
        return Decimal(str(v))
    except (InvalidOperation, ValueError) as exc:
        raise services.PortfolioError(f"Valeur numérique invalide pour {key}.") from exc


def _commodity(slug):
    if not slug:
        raise services.PortfolioError("Matière requise.")
    commodity = Commodity.objects.filter(slug=slug).first()
    if commodity is None:
        raise services.PortfolioError(f"Matière inconnue : {slug}.")
    return commodity


def _prepare(portfolio, data):
    commodity = None
    slug = data.get("commodity")
    if slug:
        commodity = Commodity.objects.filter(slug=slug).first()
        if commodity is None:
            raise services.PortfolioError(f"Matière inconnue : {slug}.")
    return services.prepare_transaction(
        portfolio,
        kind=data.get("kind"),
        date=_date(data.get("date"), dt.date.today()),
        commodity=commodity,
        amount=_decimal(data, "amount"),
        quantity=_decimal(data, "quantity"),
        note=(data.get("note") or ""),
    )


class PortfolioViewSet(viewsets.ModelViewSet):
    serializer_class = s.PortfolioSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Strict per-user isolation.
        return Portfolio.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    # -- Valuation & history -------------------------------------------------

    @action(detail=True)
    def valuation(self, request, pk=None):
        pf = self.get_object()
        try:
            as_of = _date(request.query_params.get("as_of"), dt.date.today())
        except services.PortfolioError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        data = services.value_portfolio(pf, as_of)
        return Response(s.ValuationSerializer(data).data)

    @action(detail=True)
    def history(self, request, pk=None):
        pf = self.get_object()
        try:
            start = _date(request.query_params.get("from"))
            end = _date(request.query_params.get("to"))
        except services.PortfolioError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        resolution = request.query_params.get("resolution", "daily")
        points = services.history(pf, start, end, resolution)
        return Response(s.HistoryPointSerializer(points, many=True).data)

    # -- Transactions --------------------------------------------------------

    @action(detail=True, methods=["get", "post"])
    def transactions(self, request, pk=None):
        pf = self.get_object()
        if request.method == "GET":
            qs = pf.transactions.select_related("commodity").all()
            return Response(s.TransactionSerializer(qs, many=True).data)
        try:
            txn = _prepare(pf, request.data)
            txn.save()
        except services.PortfolioError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(s.TransactionSerializer(txn).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"])
    def preview(self, request, pk=None):
        """Compute quantity/price/fee (and resulting cash) without saving."""
        pf = self.get_object()
        try:
            txn = _prepare(pf, request.data)
        except services.PortfolioError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        cash_before = services.value_portfolio(pf, txn.date)["cash"]
        if txn.kind in (Transaction.Kind.BUY, Transaction.Kind.WITHDRAW):
            cash_after = cash_before - txn.amount - txn.fee
        else:  # deposit / sell
            cash_after = cash_before + txn.amount - txn.fee
        return Response(
            {
                "kind": txn.kind,
                "date": txn.date,
                "amount": txn.amount,
                "quantity": txn.quantity,
                "unit_price": txn.unit_price,
                "fee": txn.fee,
                "cash_before": cash_before,
                "cash_after": cash_after,
            }
        )

    # -- Invest from an asset page (deposit-if-needed + buy) -----------------

    @action(detail=True, methods=["post"], url_path="invest-quote")
    def invest_quote(self, request, pk=None):
        """Breakdown + cash shortfall of a fees-included buy, without saving."""
        pf = self.get_object()
        try:
            quote = services.invest_quote(
                pf,
                _commodity(request.data.get("commodity")),
                _date(request.data.get("date"), dt.date.today()),
                _decimal(request.data, "amount"),
            )
        except services.PortfolioError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(s.InvestQuoteSerializer(quote).data)

    @action(detail=True, methods=["post"])
    def invest(self, request, pk=None):
        """Buy a commodity from its page; with ``auto_deposit`` it first tops up the
        exact missing cash, then buys (atomically)."""
        pf = self.get_object()
        try:
            created = services.invest(
                pf,
                _commodity(request.data.get("commodity")),
                _date(request.data.get("date"), dt.date.today()),
                _decimal(request.data, "amount"),
                auto_deposit=bool(request.data.get("auto_deposit")),
            )
        except services.PortfolioError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(s.TransactionSerializer(created, many=True).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=["post"], url_path="transactions/batch")
    def transactions_batch(self, request, pk=None):
        """Create several buys at once (e.g. a sector allocation). All-or-nothing."""
        pf = self.get_object()
        items = request.data.get("items", [])
        if not isinstance(items, list) or not items:
            return Response({"detail": "items requis (liste non vide)."}, status=400)
        from django.db import transaction as db_tx

        created = []
        try:
            with db_tx.atomic():
                for item in items:
                    txn = _prepare(pf, item)
                    txn.save()
                    created.append(txn)
        except services.PortfolioError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(s.TransactionSerializer(created, many=True).data, status=201)

    @action(detail=True, methods=["delete"], url_path=r"transactions/(?P<txn_id>\d+)")
    def delete_transaction(self, request, pk=None, txn_id=None):
        pf = self.get_object()
        txn = pf.transactions.filter(pk=txn_id).first()
        if txn is None:
            return Response({"detail": "Transaction introuvable."}, status=404)
        txn.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
