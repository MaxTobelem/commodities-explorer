from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import reverse
from unfold.admin import ModelAdmin, TabularInline
from unfold.decorators import action

from commodities import services

from .models import (
    Commodity,
    CommodityProduction,
    CommodityReserve,
    CommodityUsage,
    Country,
    Event,
    EventImpact,
    ImportRun,
    PriceQuote,
    Product,
    ProductComposition,
    Sector,
)

# --- Inlines ----------------------------------------------------------------


class CommodityUsageInline(TabularInline):
    model = CommodityUsage
    extra = 0
    autocomplete_fields = ["sector"]


class ProductCompositionInline(TabularInline):
    model = ProductComposition
    extra = 0
    autocomplete_fields = ["product"]


class EventImpactInline(TabularInline):
    model = EventImpact
    extra = 0
    autocomplete_fields = ["commodity"]


# --- Core entities ----------------------------------------------------------


@admin.register(Commodity)
class CommodityAdmin(ModelAdmin):
    list_display = ["name", "category", "symbol", "price_provider", "price_symbol", "is_active"]
    list_filter = ["category", "is_active", "price_provider"]
    search_fields = ["name", "symbol", "price_symbol"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [CommodityUsageInline, ProductCompositionInline, EventImpactInline]
    actions_list = ["run_full_update"]

    @action(description="Lancer une mise à jour complète")
    def run_full_update(self, request):
        """Admin button: re-run the full enrichment pass (USGS/RMIS/GDELT)."""
        run = services.enrich_data(kind=ImportRun.Kind.FULL)
        level = messages.SUCCESS if run.status == ImportRun.Status.SUCCESS else messages.ERROR
        self.message_user(request, f"Mise à jour ({run.get_status_display()}) : {run.message}", level)
        return redirect(reverse("admin:commodities_commodity_changelist"))


@admin.register(Country)
class CountryAdmin(ModelAdmin):
    list_display = ["name", "iso2", "iso3", "region"]
    list_filter = ["region"]
    search_fields = ["name", "iso2", "iso3"]


@admin.register(Sector)
class SectorAdmin(ModelAdmin):
    list_display = ["name", "nace_code"]
    search_fields = ["name", "nace_code"]
    prepopulated_fields = {"slug": ["name"]}


@admin.register(Product)
class ProductAdmin(ModelAdmin):
    list_display = ["name"]
    search_fields = ["name"]
    prepopulated_fields = {"slug": ["name"]}
    inlines = [ProductCompositionInline]


@admin.register(Event)
class EventAdmin(ModelAdmin):
    list_display = ["title", "type", "start_date", "end_date"]
    list_filter = ["type"]
    search_fields = ["title", "description"]
    prepopulated_fields = {"slug": ["title"]}
    inlines = [EventImpactInline]


# --- Relations --------------------------------------------------------------


@admin.register(PriceQuote)
class PriceQuoteAdmin(ModelAdmin):
    list_display = ["commodity", "date", "price_usd", "price_eur", "source"]
    list_filter = ["commodity", "source"]
    search_fields = ["commodity__name"]
    date_hierarchy = "date"
    list_select_related = ["commodity"]


@admin.register(CommodityReserve)
class CommodityReserveAdmin(ModelAdmin):
    list_display = ["commodity", "country", "year", "reserves_t", "source"]
    list_filter = ["year", "commodity", "source"]
    search_fields = ["commodity__name", "country__name"]
    list_select_related = ["commodity", "country"]


@admin.register(CommodityProduction)
class CommodityProductionAdmin(ModelAdmin):
    list_display = ["commodity", "country", "year", "production_t", "source"]
    list_filter = ["year", "commodity", "source"]
    search_fields = ["commodity__name", "country__name"]
    list_select_related = ["commodity", "country"]


@admin.register(CommodityUsage)
class CommodityUsageAdmin(ModelAdmin):
    list_display = ["commodity", "sector", "share_percent", "source", "needs_review"]
    list_filter = ["needs_review", "source", "sector"]
    list_editable = ["needs_review"]
    search_fields = ["commodity__name", "sector__name"]
    list_select_related = ["commodity", "sector"]


@admin.register(ProductComposition)
class ProductCompositionAdmin(ModelAdmin):
    list_display = ["product", "commodity", "role", "source", "needs_review"]
    list_filter = ["needs_review", "source"]
    list_editable = ["needs_review"]
    search_fields = ["product__name", "commodity__name"]
    list_select_related = ["product", "commodity"]


@admin.register(EventImpact)
class EventImpactAdmin(ModelAdmin):
    list_display = ["event", "commodity", "direction", "magnitude", "source", "needs_review"]
    list_filter = ["needs_review", "direction", "source"]
    list_editable = ["needs_review"]
    search_fields = ["event__title", "commodity__name"]
    list_select_related = ["event", "commodity"]


# --- Audit ------------------------------------------------------------------


@admin.register(ImportRun)
class ImportRunAdmin(ModelAdmin):
    list_display = ["kind", "status", "started_at", "finished_at"]
    list_filter = ["kind", "status"]
    readonly_fields = ["kind", "status", "started_at", "finished_at", "message"]

    def has_add_permission(self, request):
        return False
