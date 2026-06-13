"""Domain models for the commodities explorer.

Five "core" entities (Commodity, Country, Sector, Product, Event) connected by
explicit through-models that carry the quantitative/qualitative data. Each
imported row records its `source`; qualitative links also carry `needs_review`
so auto-imported data can be validated/corrected in the admin.
"""

from __future__ import annotations

from django.db import models
from django.utils import timezone


class TimeStamped(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Sourced(TimeStamped):
    """Row that records where its data came from (e.g. 'commodities-api', 'usgs')."""

    source = models.CharField(max_length=64, blank=True)

    class Meta:
        abstract = True


# --- Core entities ----------------------------------------------------------


class Commodity(TimeStamped):
    class Category(models.TextChoices):
        ENERGY = "energy", "Énergie"
        PRECIOUS = "precious", "Métal précieux"
        BASE = "base", "Métal de base / industriel"
        BATTERY = "battery", "Métal pour batteries"
        AGRICULTURAL = "agricultural", "Agricole"
        FERTILIZER = "fertilizer", "Engrais"
        OTHER = "other", "Autre"

    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    symbol = models.CharField(max_length=16, blank=True, help_text="Symbole/ticker, ex. XAU")
    category = models.CharField(max_length=16, choices=Category.choices, default=Category.OTHER)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)
    price_unit = models.CharField(
        max_length=24, default="USD/t", help_text="Unité canonique du prix, ex. USD/t, USD/ozt"
    )
    is_active = models.BooleanField(default=True)

    # Two decoupled price lanes:
    #  • Daily updates → Commodities-API via `api_symbol` (see services.update_prices).
    #  • History / monthly fallback → `price_provider` + `price_symbol` (e.g. World Bank).
    price_provider = models.CharField(
        max_length=32,
        default="commodities_api",
        help_text="Fournisseur historique / de repli (ex. worldbank, usgs_price)",
    )
    price_symbol = models.CharField(
        max_length=64,
        blank=True,
        help_text="Label côté fournisseur historique (ex. 'Gold', 'Crude oil, Brent')",
    )
    api_symbol = models.CharField(
        max_length=32,
        blank=True,
        help_text="Ticker Commodities-API pour la MAJ quotidienne (ex. XAU, BRENTOIL). "
        "Vide ⇒ pas de cours quotidien, repli sur le fournisseur historique.",
    )

    class Meta:
        verbose_name = "matière première"
        verbose_name_plural = "matières premières"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name

    @property
    def latest_quote(self) -> PriceQuote | None:
        return self.prices.order_by("-date").first()


class Country(TimeStamped):
    name = models.CharField(max_length=120, unique=True)
    iso2 = models.CharField(max_length=2, blank=True)
    iso3 = models.CharField(max_length=3, unique=True)
    region = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "pays"
        verbose_name_plural = "pays"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Sector(TimeStamped):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    nace_code = models.CharField(max_length=16, blank=True, help_text="Code NACE-2 (RMIS)")
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "secteur"
        verbose_name_plural = "secteurs"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Product(TimeStamped):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    image_url = models.URLField(blank=True)

    class Meta:
        verbose_name = "produit"
        verbose_name_plural = "produits"
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Event(TimeStamped):
    class Type(models.TextChoices):
        WAR = "war", "Conflit / Guerre"
        POLICY = "policy", "Politique / Régulation"
        DISASTER = "disaster", "Catastrophe"
        ECONOMIC = "economic", "Économique"
        OTHER = "other", "Autre"

    title = models.CharField(max_length=200, unique=True)
    slug = models.SlugField(max_length=220, unique=True)
    type = models.CharField(max_length=16, choices=Type.choices, default=Type.OTHER)
    start_date = models.DateField(null=True, blank=True)
    end_date = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True)
    source_url = models.URLField(max_length=1000, blank=True)  # Google News links are long

    class Meta:
        verbose_name = "événement"
        verbose_name_plural = "événements"
        ordering = ["-start_date", "title"]

    def __str__(self) -> str:
        return self.title


# --- Relations (through-models) ---------------------------------------------


class PriceQuote(Sourced):
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name="prices")
    date = models.DateField()
    price_usd = models.DecimalField(max_digits=16, decimal_places=4)
    price_eur = models.DecimalField(max_digits=16, decimal_places=4, null=True, blank=True)

    class Meta:
        verbose_name = "cours"
        verbose_name_plural = "cours"
        ordering = ["-date"]
        constraints = [
            models.UniqueConstraint(
                fields=["commodity", "date", "source"], name="uniq_quote_commodity_date_source"
            )
        ]

    def __str__(self) -> str:
        return f"{self.commodity} @ {self.date}: {self.price_usd} USD"


class CommodityReserve(Sourced):
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name="reserves")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="reserves")
    year = models.PositiveIntegerField()
    reserves_t = models.DecimalField(
        max_digits=22, decimal_places=2, help_text="Quantité de réserves"
    )
    unit = models.CharField(max_length=8, default="t", help_text="Unité (t, m³…)")

    class Meta:
        verbose_name = "réserve"
        verbose_name_plural = "réserves"
        ordering = ["-year", "-reserves_t"]
        constraints = [
            models.UniqueConstraint(
                fields=["commodity", "country", "year"], name="uniq_reserve_commodity_country_year"
            )
        ]

    def __str__(self) -> str:
        return f"{self.commodity} / {self.country} ({self.year}): {self.reserves_t} t"


class CommodityProduction(Sourced):
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name="production")
    country = models.ForeignKey(Country, on_delete=models.CASCADE, related_name="production")
    year = models.PositiveIntegerField()
    production_t = models.DecimalField(
        max_digits=22, decimal_places=2, help_text="Valeur de production annuelle"
    )
    unit = models.CharField(max_length=8, default="t", help_text="Unité (t, TWh…)")
    note = models.CharField(
        max_length=64,
        blank=True,
        help_text="Base de la mesure (ex. Production minière, Production d'énergie)",
    )

    class Meta:
        verbose_name = "production"
        verbose_name_plural = "productions"
        ordering = ["-year", "-production_t"]
        constraints = [
            models.UniqueConstraint(
                fields=["commodity", "country", "year"],
                name="uniq_production_commodity_country_year",
            )
        ]

    def __str__(self) -> str:
        return f"{self.commodity} / {self.country} ({self.year}): {self.production_t} t"


class CommodityUsage(Sourced):
    """Which sector uses a commodity (optionally with a consumption share %)."""

    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name="usages")
    sector = models.ForeignKey(Sector, on_delete=models.CASCADE, related_name="usages")
    share_percent = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="Part d'usage en %"
    )
    description = models.TextField(blank=True)
    needs_review = models.BooleanField(default=False)

    class Meta:
        verbose_name = "usage (secteur)"
        verbose_name_plural = "usages (secteurs)"
        ordering = ["-share_percent"]
        constraints = [
            models.UniqueConstraint(
                fields=["commodity", "sector"], name="uniq_usage_commodity_sector"
            )
        ]

    def __str__(self) -> str:
        return f"{self.commodity} → {self.sector}"


class ProductComposition(Sourced):
    """Which everyday product contains a commodity."""

    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name="compositions")
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name="compositions")
    role = models.CharField(
        max_length=200, blank=True, help_text="Rôle de la matière dans le produit"
    )
    needs_review = models.BooleanField(default=False)

    class Meta:
        verbose_name = "composition (produit)"
        verbose_name_plural = "compositions (produits)"
        ordering = ["product__name"]
        constraints = [
            models.UniqueConstraint(
                fields=["commodity", "product"], name="uniq_composition_commodity_product"
            )
        ]

    def __str__(self) -> str:
        return f"{self.product} ← {self.commodity}"


class EventImpact(Sourced):
    class Direction(models.TextChoices):
        UP = "up", "Hausse"
        DOWN = "down", "Baisse"
        NEUTRAL = "neutral", "Neutre"

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="impacts")
    commodity = models.ForeignKey(Commodity, on_delete=models.CASCADE, related_name="impacts")
    direction = models.CharField(max_length=8, choices=Direction.choices, default=Direction.NEUTRAL)
    magnitude = models.DecimalField(
        max_digits=7, decimal_places=2, null=True, blank=True, help_text="Variation estimée en %"
    )
    description = models.TextField(blank=True)
    needs_review = models.BooleanField(default=False)

    class Meta:
        verbose_name = "impact (événement)"
        verbose_name_plural = "impacts (événements)"
        ordering = ["-event__start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["event", "commodity"], name="uniq_impact_event_commodity"
            )
        ]

    def __str__(self) -> str:
        return f"{self.event} → {self.commodity} ({self.direction})"


# --- Audit ------------------------------------------------------------------


class ImportRun(models.Model):
    class Kind(models.TextChoices):
        PRICES = "prices", "Cours (quotidien)"
        ENRICH = "enrich", "Enrichissement (mensuel)"
        FULL = "full", "Mise à jour complète"

    class Status(models.TextChoices):
        RUNNING = "running", "En cours"
        SUCCESS = "success", "Succès"
        ERROR = "error", "Erreur"

    kind = models.CharField(max_length=16, choices=Kind.choices)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    message = models.TextField(blank=True)

    class Meta:
        verbose_name = "import"
        verbose_name_plural = "imports"
        ordering = ["-started_at"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} — {self.status} ({self.started_at:%Y-%m-%d %H:%M})"

    def finish(self, status: str, message: str = "") -> None:
        self.status = status
        self.message = message
        self.finished_at = timezone.now()
        self.save(update_fields=["status", "message", "finished_at"])
