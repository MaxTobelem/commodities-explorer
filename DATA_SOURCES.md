# Sources de données & mise à jour

Toutes les sources sont **gratuites** sauf **Commodities-API** (optionnelle, pour
les cours *quotidiens*). Sans clé Commodities-API, l'app tourne entièrement sur
des sources gratuites (cours mensuels World Bank).

## Tout rafraîchir en une commande

```bash
cd backend
uv run python manage.py refresh_data                      # catalogue → cours → enrichissement → curé → pays
uv run python manage.py refresh_data --skip enrich_data   # ex. sans l'enrichissement (lent)
```

Chaque étape est isolée (un échec n'interrompt pas les autres) et journalisée
dans un import `FULL` visible dans l'admin (`/admin/` → Imports).

## Récapitulatif

| Source | Alimente | Commande | Cadence | Clé |
|---|---|---|---|---|
| **World Bank** Pink Sheet | Cours mensuels (depuis 1960) + repli quotidien | `backfill_prices` / `update_prices` | mensuelle | non |
| **Commodities-API** | Cours frais USD + EUR | `update_prices` | ≤ 6 h (PRO) | **oui** |
| **USGS** MCS | Production + réserves (métaux) | `enrich_data` | annuelle | non |
| **Our World in Data** | Production (énergie, agricole) + réserves (pétrole, gaz, charbon) | `enrich_data` | annuelle | non |
| **Google Actualités** (RSS) | Actualités de marché par matière → événements | `refresh_events` | quotidienne | non |
| **Curé** (USGS, AIE, FAO…) | Secteurs d'usage % + produits | `import_curated` | manuelle | non |
| **CLDR / Babel** | Noms de pays (français) | `relabel_countries` | — | non |

## Détails & maintenance par source

### 1. Cours — World Bank (gratuit, mensuel, historique)
- **Quoi** : « Pink Sheet », 1 fichier Excel, prix mensuels USD depuis 1960.
- **Commandes** : `backfill_prices --days 25000` (tout l'historique, une seule fois) ; `update_prices` l'utilise en **repli** quand Commodities-API ne couvre pas une matière.
- **Maintenance** : l'URL du fichier change chaque année → réglage `WORLD_BANK_XLSX_URL` (env) ou `worldbank.DEFAULT_URL`. La conversion EUR est approximative via `EUR_USD_RATE`.

### 2. Cours frais — Commodities-API (payant, optionnel)
- **Quoi** : prix USD + EUR par ticker (ex. `XAU`, `BRENTOIL`). 22 matières couvertes.
- **Activer** : `COMMODITIES_API_KEY` dans `.env`. Sans clé → repli mensuel World Bank.
- **Plan & fréquence** : **PRO** (~500 $/an, 1 000 appels/mois, 10 symboles/requête) → cron **toutes les 6 h** (~365 appels/mois). Pour l'horaire, passer en **PRO PLUS** (~1 000 $/an, 15 symboles/requête) et régler `COMMODITIES_API_MAX_SYMBOLS=15`.
- **Plafond symboles/requête** : `COMMODITIES_API_MAX_SYMBOLS` (défaut 10) — `update_prices` découpe et fusionne les requêtes automatiquement (1 slot réservé à EUR).
- **Tickers** : champ `Commodity.api_symbol` (défini dans `catalog.py`, éditable en admin).
- **Valider / compléter** : `manage.py check_api_symbols` liste les tickers valides / invalides / manquants face à l'API.
- **Logique** : Commodities-API pour les matières ayant un `api_symbol`, puis World Bank comble les manques → jamais de trou.

### 3. Production & réserves métaux — USGS (gratuit)
- **Quoi** : Mineral Commodity Summaries, production + réserves par pays.
- **Commande** : `enrich_data`.
- **Maintenance** : nouvelle édition annuelle → régler `USGS_MCS_ITEM_ID` (id ScienceBase). Le mapping matière → nom USGS est dans `usgs.py` (`DEFAULT_USGS_NAMES`). Un seul **stade** de production est conservé par matière (minière > fonderie > raffinage) et étiqueté dans `note`.

### 4. Production & réserves énergie/agricole — Our World in Data (gratuit)
- **Quoi** : CSV par matière avec codes ISO3. Production (énergie en TWh, agricole en tonnes) + réserves prouvées (pétrole & charbon en t, gaz en m³).
- **Commande** : `enrich_data`.
- **Maintenance** : mappings `DEFAULT_OWID` (production) et `DEFAULT_OWID_RESERVES` (réserves) dans `owid.py` ; clés = label World Bank (`price_symbol`).

### 5. Actualités de marché — Google Actualités RSS (gratuit)
- **Quoi** : pour chaque matière, on interroge le **flux RSS de recherche** de Google Actualités en français (`news.google.com/rss/search`) ciblé sur son marché (cours, production, récolte, mine, export…). Les articles récents deviennent des événements : le **vrai titre** est le titre de l'événement, avec **lien source** et **direction** lue dans le titre via un lexique FR (flambée/pénurie → hausse, recul/surplus → baisse, sinon neutre — pas de direction inventée). 1 article par source/matière pour diversifier.
- **Commande** : `refresh_events` (quotidien, *delete-then-insert* : remplace le jeu d'actus précédent et purge les anciens « Tensions en… »). Pas de clé, pas de rate-limit pour ~39 requêtes/jour, **français direct** (zéro traduction).
- **Réglages** : `GNEWS_MAX_PER_COMMODITY` (défaut 4), `GNEWS_LOOKBACK_DAYS` (défaut 14). Les requêtes par matière (`_QUERIES`) et le lexique de direction sont dans `gnews.py`.

### 6. Secteurs & produits — dataset curé (gratuit)
- **Quoi** : parts d'usage par secteur (%) + produits du quotidien pour 22 matières, sourcés (USGS, AIE, FAO, instituts métiers).
- **Commande** : `import_curated` — autoritatif (*delete-then-insert* par matière), `source="curated"`, éditable en admin.
- **Étendre** : ajouter une entrée au dict `CURATED` dans `import_curated.py` (slug → usages / produits).

### 7. Noms de pays — CLDR / Babel (gratuit)
- **Quoi** : libellés français uniques par ISO3 (`commodities/countries.py`).
- **Commande** : `relabel_countries` (normalise l'existant). Les nouveaux imports posent déjà le nom français.

## Cron (production)

```cron
# Cours toutes les 6 h (Commodities-API plan PRO + repli World Bank)
0 */6 * * *   cd /app/backend && python manage.py update_prices
# Enrichissement complet (USGS/OWID/curé/Google News), 1×/mois
0 3 1 * *     cd /app/backend && python manage.py refresh_data --skip update_prices
# Actualités de marché (Google News), chaque jour
30 7 * * *    cd /app/backend && python manage.py refresh_events
```

À adapter au conteneur — voir [DEPLOY.md](DEPLOY.md).
