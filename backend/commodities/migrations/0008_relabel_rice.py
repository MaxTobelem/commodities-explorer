"""Switch the rice commodity to the daily Commodities-API product.

WB tracks "Rice, Thai 5%" (white rice) while Commodities-API RICE is US rough rice
— a different product. Per the chosen direction we keep the live daily CA series,
relabel the commodity to a generic "Riz", and drop the now-mismatched World Bank
Thai monthly history. No-op on a fresh database (rice not imported yet).
"""

from __future__ import annotations

from django.db import migrations


def relabel_rice(apps, schema_editor):
    Commodity = apps.get_model("commodities", "Commodity")
    PriceQuote = apps.get_model("commodities", "PriceQuote")
    rice = Commodity.objects.filter(api_symbol="RICE").first()
    if rice is None:
        return
    PriceQuote.objects.filter(commodity=rice, source="worldbank").delete()
    rice.name = "Riz"
    rice.slug = "riz"
    rice.price_symbol = ""
    rice.save(update_fields=["name", "slug", "price_symbol"])


class Migration(migrations.Migration):
    dependencies = [("commodities", "0007_commodityreserve_unit_and_more")]
    operations = [migrations.RunPython(relabel_rice, migrations.RunPython.noop)]
