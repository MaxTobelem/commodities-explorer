from django.db.models import OuterRef, QuerySet, Subquery
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

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

from . import serializers as s
from .filters import (
    CommodityFilter,
    CountryFilter,
    EventFilter,
    ProductFilter,
    SectorFilter,
)


def annotate_latest_price(qs: QuerySet) -> QuerySet:
    latest = PriceQuote.objects.filter(commodity=OuterRef("pk")).order_by("-date")
    return qs.annotate(
        latest_price_usd=Subquery(latest.values("price_usd")[:1]),
        latest_price_eur=Subquery(latest.values("price_eur")[:1]),
        latest_price_date=Subquery(latest.values("date")[:1]),
    )


class CommodityViewSet(viewsets.ReadOnlyModelViewSet):
    lookup_field = "slug"
    filterset_class = CommodityFilter
    search_fields = ["name", "symbol", "price_symbol"]
    ordering_fields = ["name", "latest_price_usd", "latest_price_date", "category"]
    ordering = ["name"]

    def get_queryset(self):
        return annotate_latest_price(Commodity.objects.all())

    def get_serializer_class(self):
        if self.action == "retrieve":
            return s.CommodityDetailSerializer
        return s.CommodityListSerializer

    @action(detail=True)
    def prices(self, request, slug=None):
        qs = PriceQuote.objects.filter(commodity=self.get_object()).order_by("date")
        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")
        if date_from:
            qs = qs.filter(date__gte=date_from)
        if date_to:
            qs = qs.filter(date__lte=date_to)
        return Response(s.PriceQuoteSerializer(qs, many=True).data)

    @action(detail=True)
    def reserves(self, request, slug=None):
        qs = (
            CommodityReserve.objects.filter(commodity=self.get_object())
            .select_related("commodity", "country")
            .order_by("-year", "-reserves_t")
        )
        return Response(s.ReserveSerializer(qs, many=True).data)

    @action(detail=True)
    def production(self, request, slug=None):
        qs = (
            CommodityProduction.objects.filter(commodity=self.get_object())
            .select_related("commodity", "country")
            .order_by("-year", "-production_t")
        )
        return Response(s.ProductionSerializer(qs, many=True).data)

    @action(detail=True)
    def usages(self, request, slug=None):
        qs = (
            CommodityUsage.objects.filter(commodity=self.get_object())
            .select_related("commodity", "sector")
            .order_by("-share_percent")
        )
        return Response(s.UsageSerializer(qs, many=True).data)

    @action(detail=True)
    def products(self, request, slug=None):
        qs = (
            ProductComposition.objects.filter(commodity=self.get_object())
            .select_related("commodity", "product")
            .order_by("product__name")
        )
        return Response(s.CompositionSerializer(qs, many=True).data)

    @action(detail=True)
    def events(self, request, slug=None):
        qs = (
            EventImpact.objects.filter(commodity=self.get_object())
            .select_related("commodity", "event")
            .order_by("-event__start_date")
        )
        return Response(s.ImpactSerializer(qs, many=True).data)


class CountryViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Country.objects.all()
    serializer_class = s.CountrySerializer
    lookup_field = "iso3"
    filterset_class = CountryFilter
    search_fields = ["name", "iso2", "iso3"]
    ordering_fields = ["name", "region"]
    ordering = ["name"]

    @action(detail=True)
    def production(self, request, iso3=None):
        qs = (
            CommodityProduction.objects.filter(country=self.get_object())
            .select_related("commodity", "country")
            .order_by("-year", "-production_t")
        )
        return Response(s.ProductionSerializer(qs, many=True).data)

    @action(detail=True)
    def reserves(self, request, iso3=None):
        qs = (
            CommodityReserve.objects.filter(country=self.get_object())
            .select_related("commodity", "country")
            .order_by("-year", "-reserves_t")
        )
        return Response(s.ReserveSerializer(qs, many=True).data)


class SectorViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Sector.objects.all()
    serializer_class = s.SectorSerializer
    lookup_field = "slug"
    filterset_class = SectorFilter
    search_fields = ["name"]
    ordering = ["name"]

    @action(detail=True)
    def commodities(self, request, slug=None):
        qs = (
            CommodityUsage.objects.filter(sector=self.get_object())
            .select_related("commodity", "sector")
            .order_by("-share_percent")
        )
        return Response(s.UsageSerializer(qs, many=True).data)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Product.objects.all()
    serializer_class = s.ProductSerializer
    lookup_field = "slug"
    filterset_class = ProductFilter
    search_fields = ["name"]
    ordering = ["name"]

    @action(detail=True)
    def commodities(self, request, slug=None):
        qs = (
            ProductComposition.objects.filter(product=self.get_object())
            .select_related("commodity", "product")
            .order_by("commodity__name")
        )
        return Response(s.CompositionSerializer(qs, many=True).data)


class EventViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Event.objects.all()
    serializer_class = s.EventSerializer
    lookup_field = "slug"
    filterset_class = EventFilter
    search_fields = ["title", "description"]
    ordering_fields = ["start_date", "title", "type"]
    ordering = ["-start_date"]

    @action(detail=True)
    def commodities(self, request, slug=None):
        qs = (
            EventImpact.objects.filter(event=self.get_object())
            .select_related("commodity", "event")
            .order_by("commodity__name")
        )
        return Response(s.ImpactSerializer(qs, many=True).data)
