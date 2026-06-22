from django.contrib import admin
from unfold.admin import ModelAdmin, TabularInline

from .models import Portfolio, Transaction


class TransactionInline(TabularInline):
    model = Transaction
    extra = 0
    fields = ("date", "kind", "commodity", "amount", "quantity", "unit_price", "fee", "note")
    ordering = ("date", "id")


@admin.register(Portfolio)
class PortfolioAdmin(ModelAdmin):
    list_display = ("name", "user", "base_currency", "fee_percent", "fee_fixed", "created_at")
    list_filter = ("base_currency",)
    search_fields = ("name", "user__username", "user__email")
    inlines = [TransactionInline]


@admin.register(Transaction)
class TransactionAdmin(ModelAdmin):
    list_display = ("portfolio", "date", "kind", "commodity", "amount", "fee")
    list_filter = ("kind", "portfolio__base_currency")
    search_fields = ("portfolio__name", "commodity__name", "note")
    date_hierarchy = "date"
