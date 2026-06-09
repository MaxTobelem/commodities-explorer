"""Faceted filters: every entity can be filtered by any other dimension."""

import django_filters as df
from django.db.models import Q

from commodities.models import Commodity, Country, Event, Product, Sector


class CommodityFilter(df.FilterSet):
    category = df.ChoiceFilter(choices=Commodity.Category.choices)
    country = df.CharFilter(method="filter_country", label="Pays (iso3) producteur/détenteur")
    sector = df.CharFilter(method="filter_sector", label="Secteur (slug)")
    product = df.CharFilter(method="filter_product", label="Produit (slug)")
    event = df.CharFilter(method="filter_event", label="Événement (slug)")
    type = df.CharFilter(method="filter_event_type", label="Type d'événement impactant")
    price_min = df.NumberFilter(method="filter_price_min")
    price_max = df.NumberFilter(method="filter_price_max")

    class Meta:
        model = Commodity
        fields = ["category"]

    def filter_country(self, qs, name, value):
        return qs.filter(
            Q(production__country__iso3__iexact=value)
            | Q(reserves__country__iso3__iexact=value)
        ).distinct()

    def filter_sector(self, qs, name, value):
        return qs.filter(usages__sector__slug=value).distinct()

    def filter_product(self, qs, name, value):
        return qs.filter(compositions__product__slug=value).distinct()

    def filter_event(self, qs, name, value):
        return qs.filter(impacts__event__slug=value).distinct()

    def filter_event_type(self, qs, name, value):
        return qs.filter(impacts__event__type=value).distinct()

    def filter_price_min(self, qs, name, value):
        return qs.filter(latest_price_usd__gte=value)

    def filter_price_max(self, qs, name, value):
        return qs.filter(latest_price_usd__lte=value)


class CountryFilter(df.FilterSet):
    commodity = df.CharFilter(method="filter_commodity", label="Matière (slug)")

    class Meta:
        model = Country
        fields = ["region"]

    def filter_commodity(self, qs, name, value):
        return qs.filter(
            Q(production__commodity__slug=value) | Q(reserves__commodity__slug=value)
        ).distinct()


class SectorFilter(df.FilterSet):
    commodity = df.CharFilter(method="filter_commodity", label="Matière (slug)")

    class Meta:
        model = Sector
        fields = []

    def filter_commodity(self, qs, name, value):
        return qs.filter(usages__commodity__slug=value).distinct()


class ProductFilter(df.FilterSet):
    commodity = df.CharFilter(method="filter_commodity", label="Matière (slug)")
    sector = df.CharFilter(method="filter_sector", label="Secteur (slug)")

    class Meta:
        model = Product
        fields = []

    def filter_commodity(self, qs, name, value):
        return qs.filter(compositions__commodity__slug=value).distinct()

    def filter_sector(self, qs, name, value):
        return qs.filter(compositions__commodity__usages__sector__slug=value).distinct()


class EventFilter(df.FilterSet):
    commodity = df.CharFilter(method="filter_commodity", label="Matière (slug)")
    type = df.ChoiceFilter(choices=Event.Type.choices)
    from_date = df.DateFilter(field_name="start_date", lookup_expr="gte")
    to_date = df.DateFilter(field_name="start_date", lookup_expr="lte")

    class Meta:
        model = Event
        fields = ["type"]

    def filter_commodity(self, qs, name, value):
        return qs.filter(impacts__commodity__slug=value).distinct()
