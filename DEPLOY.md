# Déploiement (VPS + Docker + VPN privé)

Cible : un VPS à **prix fixe** (OVH FR, Hetzner…). L'app n'est **jamais exposée
sur l'internet public** — l'accès passe par un **VPN privé** (Tailscale), ce qui
bloque tous les bots par construction. Auth applicative en plus : connexion par
code email.

Coût indicatif : ~5–7 €/mois (VPS) + Commodities-API (souvent gratuit au départ).
Tailscale (plan Personal), SMTP (tier gratuit) et GitHub = 0 €.

## 1. Préparer le VPS

Distribution : **Ubuntu Server LTS** 64-bit (24.04 ou 26.04). La version importe peu —
toute l'app tourne en **conteneurs Docker** (Python 3.12, Postgres 16, Node 20, nginx
embarqués) ; l'hôte n'a besoin que de Docker + Tailscale + rclone + cron.

```bash
# Docker + plugin compose
curl -fsSL https://get.docker.com | sh
# Si le dépôt Docker ne connaît pas encore la release (Ubuntu très récente), fallback :
#   sudo apt update && sudo apt install -y docker.io docker-compose-v2
docker --version && docker compose version
sudo usermod -aG docker "$USER"   # éviter sudo pour docker (reconnecte la session SSH ensuite)

# Pare-feu : SSH uniquement, on n'ouvre PAS 80/443 au public
sudo apt install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw enable
```

> rclone (binaire statique) et Tailscale sont insensibles à la version d'Ubuntu.

## 2. VPN privé (Tailscale)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # connecte le VPS à ton tailnet
tailscale ip -4            # note l'IP 100.x.y.z du VPS
```

Installe aussi Tailscale sur **ton desktop et ton iPad** (app officielle) et
connecte-les au **même** tailnet. Seuls ces appareils pourront atteindre l'app.

## 3. Récupérer le code et configurer

> Repo privé : ajoute une **clé de déploiement lecture-seule** sur le VPS
> (`ssh-keygen` puis GitHub → repo → Settings → Deploy keys) pour cloner/puller
> sans jamais utiliser ton compte. Le VPS ne fait que *lire* le code.

```bash
sudo mkdir -p /opt/declo && sudo chown "$USER" /opt/declo
git clone git@github.com:MaxTobelem/commodities-explorer.git /opt/declo
cd /opt/declo
cp backend/.env.prod.example backend/.env.prod
# Édite backend/.env.prod : SECRET_KEY, POSTGRES_PASSWORD + DATABASE_URL,
# ALLOWED_HOSTS + CSRF_TRUSTED_ORIGINS (nom MagicDNS *.ts.net),
# COMMODITIES_API_KEY, SMTP Mailjet…
```

## 4. Lancer la stack + charger les données

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

**Données initiales — 2 options :**

```bash
# Option A (recommandée) : restaurer un dump du dev → tout est là, AUCUN appel API
#   1) sur le Mac (dev) :  COMPOSE='docker compose' ./scripts/db_backup.sh
#   2) copier le dump sur le VPS :  scp backups/declo-*.dump user@vps:/opt/declo/backups/
#   3) sur le VPS :
./scripts/db_restore.sh ./backups/declo-AAAAMMJJ-HHMMSS.dump

# Option B : repartir de zéro (long, consomme des appels API)
docker compose -f docker-compose.prod.yml exec backend python manage.py import_commodities
docker compose -f docker-compose.prod.yml exec backend python manage.py backfill_prices --days 25000
docker compose -f docker-compose.prod.yml exec backend python manage.py refresh_data --skip update_prices
```

Puis crée ton compte (**ton email perso** = identifiant de connexion à l'app) :

```bash
docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser
```

`web` (Nginx) écoute par défaut sur `127.0.0.1:80` (jamais public).

## 5. Exposer en HTTPS sur le tailnet

`tailscale serve` termine le TLS (certificat auto) et ne sert qu'aux appareils du
tailnet :

```bash
sudo tailscale serve --bg 80    # publie http://127.0.0.1:80 en HTTPS sur le tailnet
tailscale serve status          # affiche l'URL https://<vps>.<tailnet>.ts.net
```

Ouvre cette URL depuis ton desktop/iPad (connectés au VPN) → connexion par code
email. Tout autre appareil : **injoignable**.

> `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` dans `.env.prod` doivent contenir ce nom
> d'hôte `*.ts.net`. TLS étant géré par Tailscale, on garde `SECURE_SSL_REDIRECT=False`.

## 6. Mises à jour automatiques (cron hôte)

```cron
# crontab -e
PATH=/usr/local/bin:/usr/bin:/bin
# Cours 1×/jour à 06:00 (Commodities-API + repli World Bank). ~46 symboles ⇒ 6 req/run
# ⇒ ~180 appels/mois (plafond 1000). Repasser à "0 */6 * * *" si besoin d'intraday.
0 6 * * *    cd /opt/declo && docker compose -f docker-compose.prod.yml exec -T backend python manage.py update_prices >> /home/ubuntu/declo-cron.log 2>&1
# Enrichissement + curé + pays — le 1er du mois à 05:00
0 5 1 * *    cd /opt/declo && docker compose -f docker-compose.prod.yml exec -T backend python manage.py refresh_data --skip update_prices >> /home/ubuntu/declo-cron.log 2>&1
# Actualités de marché (presse FR + mining EN + repli Google News) — chaque jour à 07:30
30 7 * * *   cd /opt/declo && docker compose -f docker-compose.prod.yml exec -T backend python manage.py refresh_events >> /home/ubuntu/declo-cron.log 2>&1
```

(Le bouton « Lancer une mise à jour complète » de l'admin reste disponible.)

## 7. Sauvegardes BDD (hors-VPS)

La base **est l'archive** (la série de cours n'est pas rejouable au-delà de ~30 j).
Sauvegarde quotidienne = **dump compressé + copie HORS-VPS via rclone**, avec rétention et
restauration testée — détails complets dans **[BACKUP.md](BACKUP.md)**.

Installer rclone une fois, puis planifier le dump quotidien + copie hors-VPS :

```bash
curl https://rclone.org/install.sh | sudo bash
rclone config   # remote « scw » : type S3, provider Scaleway, endpoint s3.fr-par.scw.cloud
```
```cron
0 4 * * *  cd /opt/declo && BACKUP_RCLONE_REMOTE=scw:declo-backups ./scripts/db_backup.sh >> /var/log/declo-backup.log 2>&1
```

Restauration sur un VPS neuf :
`./scripts/db_restore.sh scw:declo-backups/declo-AAAAMMJJ-HHMMSS.dump` (voir BACKUP.md).

## Mettre à jour l'app

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```
Les migrations s'appliquent au démarrage du conteneur `backend`.
