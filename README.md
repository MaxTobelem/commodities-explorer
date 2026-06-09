# Commodities Explorer

Dashboard privé d'exploration des **matières premières** (aluminium, cobalt, or… liste évolutive) :
cours USD/EUR, pays détenteurs/producteurs, secteurs d'usage, produits du quotidien, et événements
(conflits…) qui les impactent — le tout explorable en **filtrant sur n'importe quelle dimension**.

## Stack

- **Backend** : Django 5.2 LTS + Django REST Framework, django-filter, django-unfold (admin), PostgreSQL (SQLite en dev), `uv`.
- **Frontend** *(à venir)* : Vite + React + TypeScript + Tailwind + shadcn/ui.
- **Sources de données** : Commodities-API (cours), USGS + EU JRC RMIS (réserves/production/secteurs/produits), GDELT (conflits).

## Structure

```
backend/    # API Django + import des données
frontend/   # SPA React (à venir)
```

## Démarrage backend (dev)

```bash
cd backend
uv sync                              # installe les dépendances (Python 3.12)
cp .env.example .env                 # ajuste si besoin
uv run python manage.py migrate
uv run python manage.py seed         # jeu de données initial (idempotent)
uv run python manage.py createsuperuser
uv run python manage.py runserver    # admin sur http://localhost:8000/admin/
```

## Tests

```bash
cd backend
uv run pytest
```
