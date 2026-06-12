from rest_framework import serializers

from commodities.models import (
    Commodity,
    CommodityProduction,
    CommodityReserve,
    CommodityUsage,
    Country,
    Event,
    EventImpact,
    PriceQuote,
    Product,
    ProductComposition,
    Sector,
)

# --- Mini serializers (compact references used across cross-links) -----------


class CommodityMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Commodity
        fields = ["id", "name", "slug", "symbol", "category", "price_unit"]


class CountryMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["id", "name", "iso2", "iso3", "region"]


class SectorMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sector
        fields = ["id", "name", "slug", "nace_code"]


class ProductMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "slug", "image_url"]


class EventMiniSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ["id", "title", "slug", "type", "start_date", "end_date"]


# --- Commodity (list/detail) with annotated latest price --------------------


class CommodityListSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(source="get_category_display", read_only=True)
    # Populated by annotate_latest_price() in the viewset queryset.
    latest_price_usd = serializers.DecimalField(
        max_digits=16, decimal_places=4, allow_null=True, read_only=True
    )
    latest_price_eur = serializers.DecimalField(
        max_digits=16, decimal_places=4, allow_null=True, read_only=True
    )
    latest_price_date = serializers.DateField(allow_null=True, read_only=True)
    latest_price_source = serializers.CharField(allow_null=True, read_only=True)
    sparkline = serializers.SerializerMethodField()

    class Meta:
        model = Commodity
        fields = [
            "id", "name", "slug", "symbol", "category", "category_display",
            "price_unit", "image_url",
            "latest_price_usd", "latest_price_eur", "latest_price_date",
            "latest_price_source", "sparkline",
        ]

    def get_sparkline(self, obj) -> list[float]:
        # Last 30 daily USD prices (oldest→newest) for a card sparkline.
        prices = obj.prices.order_by("-date").values_list("price_usd", flat=True)[:30]
        return [float(p) for p in reversed(list(prices))]


class CommodityDetailSerializer(CommodityListSerializer):
    class Meta(CommodityListSerializer.Meta):
        fields = CommodityListSerializer.Meta.fields + [
            "description", "is_active", "price_provider", "price_symbol",
        ]


# --- Through-model serializers (carry both ends + data; reused both ways) ----


class PriceQuoteSerializer(serializers.ModelSerializer):
    class Meta:
        model = PriceQuote
        fields = ["date", "price_usd", "price_eur", "source"]


class ReserveSerializer(serializers.ModelSerializer):
    commodity = CommodityMiniSerializer(read_only=True)
    country = CountryMiniSerializer(read_only=True)

    class Meta:
        model = CommodityReserve
        fields = ["commodity", "country", "year", "reserves_t", "unit", "source"]


class ProductionSerializer(serializers.ModelSerializer):
    commodity = CommodityMiniSerializer(read_only=True)
    country = CountryMiniSerializer(read_only=True)

    class Meta:
        model = CommodityProduction
        fields = ["commodity", "country", "year", "production_t", "unit", "note", "source"]


class UsageSerializer(serializers.ModelSerializer):
    commodity = CommodityMiniSerializer(read_only=True)
    sector = SectorMiniSerializer(read_only=True)

    class Meta:
        model = CommodityUsage
        fields = ["commodity", "sector", "share_percent", "description", "source", "needs_review"]


class CompositionSerializer(serializers.ModelSerializer):
    commodity = CommodityMiniSerializer(read_only=True)
    product = ProductMiniSerializer(read_only=True)

    class Meta:
        model = ProductComposition
        fields = ["commodity", "product", "role", "source", "needs_review"]


class ImpactSerializer(serializers.ModelSerializer):
    commodity = CommodityMiniSerializer(read_only=True)
    event = EventMiniSerializer(read_only=True)
    direction_display = serializers.CharField(source="get_direction_display", read_only=True)

    class Meta:
        model = EventImpact
        fields = [
            "commodity", "event", "direction", "direction_display",
            "magnitude", "description", "source", "needs_review",
        ]


# --- Full detail serializers for the non-commodity entities ------------------


class CountrySerializer(serializers.ModelSerializer):
    class Meta:
        model = Country
        fields = ["id", "name", "iso2", "iso3", "region"]


class SectorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sector
        fields = ["id", "name", "slug", "nace_code", "description"]


class ProductSerializer(serializers.ModelSerializer):
    class Meta:
        model = Product
        fields = ["id", "name", "slug", "description", "image_url"]


class EventSerializer(serializers.ModelSerializer):
    type_display = serializers.CharField(source="get_type_display", read_only=True)

    class Meta:
        model = Event
        fields = [
            "id", "title", "slug", "type", "type_display",
            "start_date", "end_date", "description", "source_url",
        ]
