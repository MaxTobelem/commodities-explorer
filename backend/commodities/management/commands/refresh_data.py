"""One command to refresh every data source (cron or manual).

Runs, in order: catalogue → daily prices → enrichment (production / reserves /
usages / events) → curated dataset → country-name normalisation. Each step is
isolated so one failure doesn't abort the rest; a FULL ImportRun records the
outcome. Use ``--skip`` to leave out steps (e.g. the slow enrichment).
"""

from __future__ import annotations

from django.core.management import call_command
from django.core.management.base import BaseCommand

from commodities.models import ImportRun

# (command, human label) — order matters (curated overrides enriched usages).
STEPS = [
    ("import_commodities", "Catalogue des matières"),
    ("update_prices", "Cours (Commodities-API quotidien + repli World Bank)"),
    ("enrich_data", "Production / réserves / usages / actualités (USGS, OWID, presse+mining+Google News)"),
    ("import_curated", "Secteurs d'usage & produits (dataset curé)"),
    ("relabel_countries", "Uniformisation des noms de pays"),
]


class Command(BaseCommand):
    help = "Rafraîchit TOUTES les sources (catalogue, cours, enrichissement, curé, pays)."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--skip",
            nargs="*",
            default=[],
            metavar="STEP",
            help="Étapes à ignorer, ex. --skip enrich_data update_prices",
        )

    def handle(self, *args, **options) -> None:
        skip = set(options["skip"])
        run = ImportRun.objects.create(kind=ImportRun.Kind.FULL)
        done: list[str] = []
        failed: list[str] = []
        for name, label in STEPS:
            if name in skip:
                self.stdout.write(self.style.WARNING(f"⏭  {label} [{name}] — ignoré"))
                continue
            self.stdout.write(self.style.MIGRATE_HEADING(f"▶ {label} [{name}]"))
            try:
                call_command(name)
                done.append(name)
            except Exception as exc:  # noqa: BLE001 — isolate per-step failures
                failed.append(f"{name}: {type(exc).__name__}: {exc}")
                self.stderr.write(self.style.ERROR(f"  ✗ {name}: {exc}"))

        message = f"{len(done)}/{len(STEPS) - len(skip)} étapes OK : {', '.join(done) or '—'}."
        if failed:
            message += " Échecs : " + " | ".join(failed)
        run.finish(ImportRun.Status.ERROR if failed else ImportRun.Status.SUCCESS, message)
        style = self.style.ERROR if failed else self.style.SUCCESS
        self.stdout.write(style(f"Terminé — {message}"))
