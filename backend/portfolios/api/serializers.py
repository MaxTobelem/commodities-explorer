from rest_framework import serializers

from portfolios.models import Portfolio, Transaction


class CommodityMiniSerializer(serializers.Serializer):
    slug = serializers.CharField()
    name = serializers.CharField()
    symbol = serializers.CharField()
    price_unit = serializers.CharField()


# --- Read serializers -------------------------------------------------------


class TransactionSerializer(serializers.ModelSerializer):
    kind_display = serializers.CharField(source="get_kind_display", read_only=True)
    commodity = CommodityMiniSerializer(read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "date", "kind", "kind_display", "commodity",
            "amount", "quantity", "unit_price", "fee", "note", "created_at",
        ]


class _Decimal2(serializers.DecimalField):
    def __init__(self, **kwargs):
        super().__init__(max_digits=18, decimal_places=2, **kwargs)


class PositionSerializer(serializers.Serializer):
    commodity = CommodityMiniSerializer()
    quantity = serializers.DecimalField(max_digits=24, decimal_places=8)
    avg_cost = serializers.DecimalField(max_digits=18, decimal_places=4)
    price = serializers.DecimalField(max_digits=18, decimal_places=4)
    cost_basis = _Decimal2()
    market_value = _Decimal2()
    unrealized_pnl = _Decimal2()
    weight = serializers.DecimalField(max_digits=7, decimal_places=2)


class ValuationSerializer(serializers.Serializer):
    as_of = serializers.DateField()
    currency = serializers.CharField()
    cash = _Decimal2()
    invested = _Decimal2()
    positions_value = _Decimal2()
    total_value = _Decimal2()
    net_deposits = _Decimal2()
    realized_pnl = _Decimal2()
    unrealized_pnl = _Decimal2()
    total_pnl = _Decimal2()
    total_pnl_pct = serializers.DecimalField(max_digits=10, decimal_places=2)
    fees_total = _Decimal2()
    positions = PositionSerializer(many=True)


class HistoryPointSerializer(serializers.Serializer):
    date = serializers.DateField()
    value = _Decimal2()
    invested = _Decimal2()
    cash = _Decimal2()


class PortfolioSummarySerializer(serializers.Serializer):
    currency = serializers.CharField()
    cash = _Decimal2()
    total_value = _Decimal2()
    total_pnl = _Decimal2()
    total_pnl_pct = serializers.DecimalField(max_digits=10, decimal_places=2)


# --- Portfolio CRUD ---------------------------------------------------------


class PortfolioSerializer(serializers.ModelSerializer):
    summary = serializers.SerializerMethodField()

    class Meta:
        model = Portfolio
        fields = [
            "id", "name", "base_currency", "description",
            "fee_percent", "fee_fixed", "created_at", "summary",
        ]

    def get_summary(self, obj) -> dict:
        from portfolios import services

        v = services.value_portfolio(obj)
        return PortfolioSummarySerializer(v).data

    def update(self, instance, validated_data):
        # Currency is frozen once the journal has entries (no mixing currencies).
        new_currency = validated_data.get("base_currency")
        if new_currency and new_currency != instance.base_currency and instance.has_transactions:
            raise serializers.ValidationError(
                {"base_currency": "Devise non modifiable : le portefeuille a déjà des transactions."}
            )
        return super().update(instance, validated_data)
