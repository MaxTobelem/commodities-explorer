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
| **Presse RSS** (éditeurs FR) | Actualités **avec résumé** (énergie/agri) → événements | `refresh_events` | quotidienne | non |
| **Mining press** (éditeurs EN) | Actualités **métaux avec résumé** (en anglais) → événements | `refresh_events` | quotidienne | non |
| **Google Actualités** (RSS) | Repli actus pour les matières non couvertes ci-dessus | `refresh_events` | quotidienne | non |
| **Curé** (USGS, AIE, FAO…) | Secteurs d'usage % + produits | `import_curated` | manuelle | non |
| **CLDR / Babel** | Noms de pays (français) | `relabel_countries` | — | non |

## Détails & maintenance par source

### 1. Cours — World Bank (gratuit, mensuel, historique)
- **Quoi** : « Pink Sheet », 1 fichier Excel, prix mensuels USD depuis 1960.
- **Commandes** : `backfill_prices --days 25000` (tout l'historique, une seule fois) ; `update_prices` l'utilise en **repli** quand Commodities-API ne couvre pas une matière.
- **Maintenance** : l'URL du fichier change chaque année → réglage `WORLD_BANK_XLSX_URL` (env) ou `worldbank.DEFAULT_URL`. La conversion EUR est approximative via `EUR_USD_RATE`.

### 2. Cours frais — Commodities-API (payant, optionnel)
- **Quoi** : prix USD + EUR par ticker (ex. `XAU`, `BRENTOIL`). 46 matières couvertes (les autres → repli mensuel World Bank). Compléter via `check_api_symbols` + `calibrate_api_units` (valide le facteur d'unité avant de mapper ; indispensable pour les matières absentes de World Bank).
- **Activer** : `COMMODITIES_API_KEY` dans `.env`. Sans clé → repli mensuel World Bank.
- **Plan & fréquence** : **PRO** (~500 $/an, 1 000 appels/mois, 10 symboles/requête). 46 symboles ⇒ 6 requêtes/run ; cron **1×/jour** ⇒ ~180 appels/mois. (Toutes les 6 h ⇒ ~720/mois, possible mais plus serré, surtout avec un backfill.) Pour plus de symboles/requête, passer en **PRO PLUS** (~1 000 $/an, 15 symboles/requête) et régler `COMMODITIES_API_MAX_SYMBOLS=15`.
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

### 5. Actualités de marché — presse RSS (FR + EN) + repli Google Actualités (gratuit)
Trois sources coordonnées par `refresh_events` (quotidien, **archive glissante de 31 jours** : les articles frais sont mis à jour/insérés, puis les actus au-delà de la fenêtre — ou non datées — qui ne sont plus dans les flux sont purgées ; réglage `EVENT_RETENTION_DAYS` dans `services.py`). Direction (flambée/pénurie → hausse, recul/repli → baisse, sinon neutre) et catégorie (guerre / catastrophe / politique / marché) sont lues dans des lexiques partagés (`newslex.py` : FR + scorers génériques réutilisés par le lexique EN de `mining.py`). Aucune clé, aucune direction inventée. Règle anti-bruit commune : le terme matière doit apparaître **dans le titre** *et* le titre doit porter un signal de marché.

- **Primaire FR — presse (`presse.py`)** : flux d'**éditeurs français** dont chaque article porte un **vrai résumé** (chapô) → **vraie description**. Couvre surtout **énergie + agricole + engrais** (Connaissance des Énergies, La France Agricole, Terre-net, Web-agri, Le Monde, Le Figaro). Mots ambigus (or, argent, fer, bois, gaz) → expression désambiguïsée ; un article peut concerner plusieurs matières (1 événement, N impacts). Réglages : `PRESSE_*` ; flux = `FEEDS`, mapping = `_PATTERNS` dans `presse.py`.
- **Primaire EN — mining (`mining.py`)** : pour les **métaux** (cuivre, or, argent, nickel, zinc, plomb, étain, aluminium, minerai de fer, platine, cobalt), flux de la **presse minière anglophone** avec vrai résumé (Mining.com, The Northern Miner), faute d'équivalent FR frais. Matching/scoring sur l'anglais (lexiques EN), puis titre + résumé **traduits en français** (`deep-translator`, gratuit, repli anglais si échec). Réglages : `MINING_*` (dont `MINING_TRANSLATE`).
- **Repli — Google Actualités (`gnews.py`)** : pour ce que presse + mining ne couvrent pas (**softs tropicaux**, produits de niche, métaux sans actu du jour), flux RSS de recherche Google en français, ciblé par matière. Vrai titre, **pas de vraie description** (le lien Google masque l'article). Réglages : `GNEWS_*` ; requêtes dans `_QUERIES`.
- **Étendre** : ajouter un flux à `presse.FEEDS` ou `mining.FEEDS` (vérifier qu'il est **frais** et que `<description>` porte un vrai chapô), et au besoin un motif à `_PATTERNS`. Manque toujours : un flux **softs tropicaux** (cacao, café, coton…) frais avec résumés (Agence Ecofin = chapôs riches mais flux gelés ; Commodafrica = 503).

### 6. Secteurs & produits — dataset curé (gratuit)
- **Quoi** : parts d'usage par secteur (%) + produits du quotidien pour 22 matières, sourcés (USGS, AIE, FAO, instituts métiers).
- **Commande** : `import_curated` — autoritatif (*delete-then-insert* par matière), `source="curated"`, éditable en admin.
- **Étendre** : ajouter une entrée au dict `CURATED` dans `import_curated.py` (slug → usages / produits).

### 7. Noms de pays — CLDR / Babel (gratuit)
- **Quoi** : libellés français uniques par ISO3 (`commodities/countries.py`).
- **Commande** : `relabel_countries` (normalise l'existant). Les nouveaux imports posent déjà le nom français.

### 8. Indices financiers — export iMGP (gratuit, historique)
- **Quoi** : indices boursiers, obligataires, high yield, hedge funds, CTA, monétaire (actions/oblig/HY/HF/CTA/cash), + IPC (inflation US & zone euro) et le change EUR/USD, en **niveaux base 100 mensuels** (depuis 1969-1999 selon la série, jusqu'à fin 2021). Servent à l'**idée 2** (backtest historique + risque), aux côtés des matières.
- **Modèles** : `markets.MarketAsset` / `markets.AssetPrice` (une valeur datée — supporte le mensuel **et** le journalier sans changement de schéma).
- **Commande** : `import_market_assets` — idempotent (*upsert* méta + remplacement de la série), `source="imgp_csv"`. CSV embarqués dans `backend/markets/seed/` (séparateur `;`, dates `%d/%m/%Y`, BOM).
- **Devises** : chaque indice est coté dans sa devise (USD pour la plupart, EUR pour le monétaire/IPC zone euro) et **converti** vers la devise du backtest via la série `EURBGN` (USD pour 1 EUR), série temporelle — pas de taux fixe.
- **Mapping** : `markets/catalog.py` (ticker → nom, classe d'actif, devise). Les variantes couvertes EUR (`_HDG`) ne sont pas importées (la conversion FX suffit).
- **Étendre** : brancher un provider (API payante journalière) sur le même modèle, sans refonte ; ajouter un ticker = une entrée dans `catalog.ASSETS` + le CSV correspondant.

## Couverture & limites connues (maintenance)

**58 matières** : **46 en cours quotidien** (Commodities-API) + **12 en mensuel** (World Bank).

**Les 12 en mensuel uniquement** — pas de ticker Commodities-API propre/calibrable (`calibrate_api_units` n'a pas donné de facteur d'unité fiable) :
Gaz naturel (Europe), Thé, Huile de tournesol, Orge, Bœuf, Crevettes, Caoutchouc, Bois (grumes), Tabac, Phosphate (roche), DAP (engrais), Chlorure de potassium.
→ Pour en passer une en quotidien : `check_api_symbols` (le ticker existe-t-il ?) puis `calibrate_api_units` ; ne mapper que si le facteur d'unité ressort propre.

**Producteurs par pays (USGS / OWID)** — n'existent que pour les matières que ces sources couvrent. Parmi les 19 ajoutées en quotidien, **seul le magnésium** (USGS `"Magnesium metal"`) a des « Principaux producteurs » ; les **18 autres restent vides** (sans source publique par pays) : uranium (= EIA, non câblé), palladium/rhodium (PGM regroupés chez USGS), acier/ferraille, WTI, naphta, méthanol, essence, éthanol, plastiques (PVC/PP), colza, porc, café robusta, avoine, saumon, huile de coco. OWID s'indexe sur le label World Bank (`price_symbol`), que ces matières n'ont pas.

**Candidats `/symbols` écartés** (données API douteuses, non ajoutés au catalogue) : Lithium (aucun facteur net), Manganèse (`0.0001` cassé), Propane (= copie d'uranium), Germanium (×5 trop haut), Dysprosium (×2), Molybdène / Titane / Tungstène / Ferrosilicium (grade ambigu), Diesel, Jus d'orange (ticker = fruit), Laine, Polyéthylène / Soude / Pâte à papier (cotés en RMB → facteur fixe impossible). Réévaluables avec `calibrate_api_units`. Antimoine / Néodyme / Gallium / Ferrochrome : *per-once-troy* plausible mais ~65 % de confiance — ajoutables flaggés si besoin.

## Cron (production)

```cron
# Cours 1×/jour (Commodities-API plan PRO + repli World Bank)
0 6 * * *     cd /app/backend && python manage.py update_prices
# Enrichissement complet (USGS/OWID/curé/presse+mining+Google News), 1×/mois
0 3 1 * *     cd /app/backend && python manage.py refresh_data --skip update_prices
# Actualités de marché (presse FR + mining EN + repli Google News), chaque jour
30 7 * * *    cd /app/backend && python manage.py refresh_events
```

À adapter au conteneur — voir [DEPLOY.md](DEPLOY.md).
