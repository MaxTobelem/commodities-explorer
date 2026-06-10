# Commodities Explorer

Dashboard privé d'exploration des **matières premières** (aluminium, cobalt, or… liste évolutive) :
cours USD/EUR, pays détenteurs/producteurs, secteurs d'usage, produits du quotidien, et événements
(conflits…) qui les impactent — le tout explorable en **filtrant sur n'importe quelle dimension**.

## Stack

- **Backend** : Django 5.2 LTS + Django REST Framework, django-filter, django-unfold (admin), PostgreSQL (SQLite en dev), `uv`.
- **Frontend** : Vite + React + TypeScript + Tailwind v4 + shadcn/ui, TanStack Query, Recharts, react-router.
- **Sources de données** : World Bank Pink Sheet (cours mensuels depuis 1960) + **Commodities-API** (cours quotidiens, optionnel) + USGS (production/réserves métaux) + Our World in Data (production & réserves énergie/agricole) + dataset curé (secteurs/produits) + GDELT (conflits). Détails & maintenance : **[DATA_SOURCES.md](DATA_SOURCES.md)**.

## Structure

```
backend/    # API Django + import des données
frontend/   # SPA React (explorateur à facettes)
```

## Démarrage en dev (hybride : Postgres via Docker, apps en natif)

```bash
# 1. Base de données (depuis la racine du repo)
docker compose up -d db

# 2. Backend
cd backend
uv sync                              # dépendances (Python 3.12)
cp .env.example .env                 # DATABASE_URL pointe déjà sur le Postgres Docker
uv run python manage.py migrate
uv run python manage.py import_commodities             # catalogue complet (~39 matières)
uv run python manage.py seed                           # démo : pays, secteurs, produits, événements (idempotent)
uv run python manage.py import_curated                 # secteurs d'usage % + produits (curé, sourcé, éditable en admin)
uv run python manage.py update_prices                  # derniers cours (World Bank + USGS cobalt)
uv run python manage.py backfill_prices --days 25000   # historique des cours (depuis 1960)
uv run python manage.py enrich_data                    # production/réserves (USGS minerais + OWID énergie/agricole) + conflits GDELT
uv run python manage.py createsuperuser
uv run python manage.py runserver 127.0.0.1:8001       # port 8001 (évite :8000 occupé) — admin sur /admin/
```

## Démarrage frontend (dev)

```bash
cd frontend
npm install
npm run dev    # http://localhost:5173 (proxy /api → http://127.0.0.1:8001)
```

Le backend doit tourner en parallèle. Crée un compte (email) via `createsuperuser`
ou l'admin, puis connecte-toi : saisis ton email → un **code** est envoyé (en dev,
il s'affiche dans la console du serveur Django) → entre le code.

## Mettre à jour les données

Tout en une commande (catalogue → cours → enrichissement → curé → pays) :

```bash
cd backend
uv run python manage.py refresh_data
```

Pour les **cours quotidiens**, renseigner `COMMODITIES_API_KEY` dans `.env` puis
valider les tickers avec `uv run python manage.py check_api_symbols`. Sans clé, les
cours restent mensuels (World Bank). Détail et maintenance de chaque source :
**[DATA_SOURCES.md](DATA_SOURCES.md)**.

## Sauvegardes

La base est l'archive (cours accumulés non rejouables au-delà de ~30 j). Sauvegarde
quotidienne hors-VPS (dump compressé + rclone) avec restauration testée :
**[BACKUP.md](BACKUP.md)**.

## Tests

```bash
cd backend
uv run pytest
```
