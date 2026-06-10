#!/usr/bin/env bash
# Restauration de la base Postgres depuis un dump (chemin LOCAL ou remote RCLONE).
# Usage :
#   ./scripts/db_restore.sh ./backups/declo-20260610-040000.dump
#   ./scripts/db_restore.sh b2:declo-backups/declo-20260610-040000.dump
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose -f docker-compose.prod.yml}"
src="${1:?usage: db_restore.sh <dump local | remote:chemin>}"

cleanup=""
case "$src" in
  *:*)  # ressemble à un remote rclone (remote:chemin) → on le télécharge d'abord
    cleanup="$(mktemp)"
    echo "[restore] récupération de $src"
    rclone copyto "$src" "$cleanup"
    src="$cleanup"
    ;;
esac
[ -s "$src" ] || { echo "[restore] fichier introuvable ou vide : $src" >&2; exit 1; }

echo "[restore] ⚠ Cette opération ÉCRASE la base actuelle. Démarrage dans 5 s (Ctrl-C pour annuler)…"
sleep 5
$COMPOSE exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists --no-owner' < "$src"
[ -n "$cleanup" ] && rm -f "$cleanup"
echo "[restore] terminé."
