"""Normalise every Country.name to its canonical French label (CLDR/Babel).

Country names accumulate from several sources (seed, USGS, OWID) in mixed
languages; this one-shot command rewrites them consistently. Safe to re-run.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import IntegrityError, transaction

from commodities.countries import french_name
from commodities.models import Country


class Command(BaseCommand):
    help = "Uniformise les noms de pays en français (source unique CLDR/Babel)."

    def handle(self, *args, **options) -> None:
        renamed = skipped = 0
        for country in Country.objects.all():
            target = french_name(country.iso3, country.name)
            if target == country.name:
                continue
            try:
                with transaction.atomic():
                    country.name = target
                    country.save(update_fields=["name"])
                renamed += 1
                self.stdout.write(f"  {country.iso3}: → {target}")
            except IntegrityError:
                skipped += 1
                self.stderr.write(f"  {country.iso3}: conflit de nom « {target} » — ignoré")
        self.stdout.write(self.style.SUCCESS(f"{renamed} pays renommés, {skipped} ignorés."))
