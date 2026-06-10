#!/usr/bin/env bash
# Sauvegarde Postgres : dump compressé local + copie HORS-VPS (rclone) + rétention.
# Conçu pour la stack prod (docker-compose.prod.yml). Idempotent, sûr en cron.
#
# Cron quotidien (exemple) :
#   0 4 * * *  cd /opt/declo && BACKUP_RCLONE_REMOTE=b2:declo-backups ./scripts/db_backup.sh >> /var/log/declo-backup.log 2>&1
#
# Variables (toutes optionnelles) :
#   COMPOSE                  commande compose (déf. "docker compose -f docker-compose.prod.yml")
#   BACKUP_DIR               dossier des dumps locaux (déf. ./backups)
#   BACKUP_KEEP_LOCAL        nb de dumps locaux conservés (déf. 14)
#   BACKUP_RCLONE_REMOTE     remote rclone, ex. b2:declo-backups (vide = local seulement)
#   BACKUP_REMOTE_KEEP_DAYS  rétention distante en jours (déf. 90)
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE="${COMPOSE:-docker compose -f docker-compose.prod.yml}"
BACKUP_DIR="${BACKUP_DIR:-./backups}"
KEEP_LOCAL="${BACKUP_KEEP_LOCAL:-14}"
RCLONE_REMOTE="${BACKUP_RCLONE_REMOTE:-}"
REMOTE_KEEP_DAYS="${BACKUP_REMOTE_KEEP_DAYS:-90}"

mkdir -p "$BACKUP_DIR"
file="$BACKUP_DIR/declo-$(date +%Y%m%d-%H%M%S).dump"

echo "[backup $(date +%FT%T)] dump → $file"
# pg_dump dans le conteneur (format custom compressé), via les identifiants du conteneur.
if ! $COMPOSE exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc'  > "$file"; then
  echo "[backup] ERREUR pg_dump" >&2; rm -f "$file"; exit 1
fi
[ -s "$file" ] || { echo "[backup] ERREUR : dump vide" >&2; rm -f "$file"; exit 1; }
echo "[backup] taille $(du -h "$file" | cut -f1)"

# Copie hors-VPS (la protection contre une perte du VPS).
if [ -n "$RCLONE_REMOTE" ]; then
  echo "[backup] rclone copy → $RCLONE_REMOTE/"
  rclone copy "$file" "$RCLONE_REMOTE/" --no-traverse
  # Rétention distante : purge les dumps plus vieux que N jours (ne touche jamais les récents).
  rclone delete "$RCLONE_REMOTE/" --min-age "${REMOTE_KEEP_DAYS}d" --include 'declo-*.dump' || true
else
  echo "[backup] (aucun remote rclone configuré — copie locale seulement)"
fi

# Rétention locale : garde les KEEP_LOCAL dumps les plus récents.
( ls -1t "$BACKUP_DIR"/declo-*.dump 2>/dev/null || true ) | tail -n +"$((KEEP_LOCAL + 1))" | while read -r old; do
  echo "[backup] purge $old"; rm -f "$old"
done
echo "[backup] OK"
