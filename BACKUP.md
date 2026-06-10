# Sauvegarde & restauration de la base

La base de données **est l'archive** : elle accumule la série de cours (Commodities-API
n'expose l'historique que ~30 jours), et tout re-fetcher coûte du temps et des appels API.
Stratégie : **dump compressé quotidien** + **copie hors-VPS** (object storage via rclone),
avec rétention et restauration testée.

> Le reste des données (historique 1960 World Bank, production/réserves USGS·OWID,
> événements GDELT, dataset curé) est rejouable gratuitement via `refresh_data` — seule
> la série de cours accumulée justifie vraiment les sauvegardes.

## Coût

Un dump pèse **~0,65 Mo**. Même à 4 sauvegardes/jour sur 90 jours conservés, on stocke
< 0,25 Go → **gratuit** chez tous les fournisseurs (Cloudflare R2 et Backblaze B2 : 10 Go
gratuits ; Scaleway : 75 Go). La fréquence n'a aucun impact de coût.

## Mise en place (sur le VPS)

### 1. Installer et configurer rclone (une fois)

```bash
curl https://rclone.org/install.sh | sudo bash
rclone config        # créer un remote (ex. Backblaze B2 / Cloudflare R2 / Scaleway)
```

Crée un bucket dédié (ex. `declo-backups`). Le remote rclone se référence ensuite
`NOM_DU_REMOTE:bucket`, par ex. `b2:declo-backups`.

### 2. Tester une sauvegarde manuelle

```bash
cd /opt/declo            # racine du repo sur le VPS
BACKUP_RCLONE_REMOTE=b2:declo-backups ./scripts/db_backup.sh
ls -lh backups/          # dump local
rclone ls b2:declo-backups   # dump distant
```

### 3. Planifier (cron) — quotidien à 04:00

```cron
0 4 * * *  cd /opt/declo && BACKUP_RCLONE_REMOTE=b2:declo-backups ./scripts/db_backup.sh >> /var/log/declo-backup.log 2>&1
```

Pour **toutes les 6 h** : `0 */6 * * *`. Pour **toutes les 12 h** : `0 */12 * * *`. (Même coût.)

## Rétention

- **Local** : les `BACKUP_KEEP_LOCAL` derniers dumps (défaut **14**).
- **Distant** : dumps des `BACKUP_REMOTE_KEEP_DAYS` derniers jours (défaut **90**).

Réglables par variables d'environnement (voir l'entête de `scripts/db_backup.sh`).

## Restauration

Depuis un dump **distant** (cas « le VPS est mort, je repars de zéro ») :

```bash
# Sur le nouveau VPS, après `docker compose -f docker-compose.prod.yml up -d db` :
rclone ls b2:declo-backups                                   # lister les dumps
./scripts/db_restore.sh b2:declo-backups/declo-AAAAMMJJ-HHMMSS.dump
```

Depuis un dump **local** :

```bash
./scripts/db_restore.sh ./backups/declo-AAAAMMJJ-HHMMSS.dump
```

`db_restore.sh` télécharge le dump si besoin, puis `pg_restore --clean --if-exists`
(écrase et recharge la base). ⚠ Opération destructive : 5 s de délai d'annulation.

## Vérifier l'intégrité d'un dump (sans écraser la prod)

```bash
# Restaure dans une base jetable et compte les lignes, puis nettoie.
docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "CREATE DATABASE verif;"
docker compose -f docker-compose.prod.yml exec -T db sh -c 'pg_restore -U "$POSTGRES_USER" -d verif --no-owner' < backups/declo-XXXX.dump
docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" -d verif -c "select count(*) from commodities_pricequote;"
docker compose -f docker-compose.prod.yml exec -T db psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "DROP DATABASE verif;"
```

## Bonnes pratiques

- **Tester la restauration** au moins une fois après la mise en place (et ~1×/trimestre).
- Garder le **secret rclone** hors du repo (il vit dans `~/.config/rclone/rclone.conf` sur le VPS).
- Une copie supplémentaire est facile à ajouter (2ᵉ remote rclone, ou tirage vers le Mac
  via Tailscale : `scp` du dernier `backups/declo-*.dump`).
