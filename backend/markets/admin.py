from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import AssetPrice, MarketAsset


@admin.register(MarketAsset)
class MarketAssetAdmin(ModelAdmin):
    list_display = ("code", "name", "asset_class", "currency", "source")
    list_filter = ("asset_class", "currency")
    search_fields = ("code", "name")


@admin.register(AssetPrice)
class AssetPriceAdmin(ModelAdmin):
    list_display = ("asset", "date", "value")
    list_filter = ("asset",)
    date_hierarchy = "date"
