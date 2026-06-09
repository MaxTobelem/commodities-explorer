# Déploiement (VPS + Docker + VPN privé)

Cible : un VPS à **prix fixe** (OVH FR, Hetzner…). L'app n'est **jamais exposée
sur l'internet public** — l'accès passe par un **VPN privé** (Tailscale), ce qui
bloque tous les bots par construction. Auth applicative en plus : connexion par
code email.

Coût indicatif : ~5–7 €/mois (VPS) + Commodities-API (souvent gratuit au départ).
Tailscale (plan Personal), SMTP (tier gratuit) et GitHub = 0 €.

## 1. Préparer le VPS

```bash
# Docker + compose plugin
curl -fsSL https://get.docker.com | sh
# Pare-feu : SSH uniquement, on n'ouvre PAS 80/443 au public
sudo apt install -y ufw
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp
sudo ufw enable
```

## 2. VPN privé (Tailscale)

```bash
curl -fsSL https://tailscale.com/install.sh | sh
sudo tailscale up          # connecte le VPS à ton tailnet
tailscale ip -4            # note l'IP 100.x.y.z du VPS
```

Installe aussi Tailscale sur **ton desktop et ton iPad** (app officielle) et
connecte-les au **même** tailnet. Seuls ces appareils pourront atteindre l'app.

## 3. Récupérer le code et configurer

```bash
git clone git@github.com:MaxTobelem/commodities-explorer.git
cd commodities-explorer
cp backend/.env.prod.example backend/.env.prod
# Édite backend/.env.prod : SECRET_KEY, POSTGRES_PASSWORD + DATABASE_URL,
# ALLOWED_HOSTS (nom MagicDNS Tailscale), COMMODITIES_API_KEY, SMTP…
```

## 4. Lancer la stack

```bash
docker compose -f docker-compose.prod.yml up -d --build
docker compose -f docker-compose.prod.yml exec backend python manage.py createsuperuser
docker compose -f docker-compose.prod.yml exec backend python manage.py seed
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
# Cours quotidiens (06:00)
0 6 * * *  cd /home/USER/commodities-explorer && docker compose -f docker-compose.prod.yml exec -T backend python manage.py update_prices
# Enrichissement mensuel (le 1er à 05:00)
0 5 1 * *  cd /home/USER/commodities-explorer && docker compose -f docker-compose.prod.yml exec -T backend python manage.py enrich_data
```

(Le bouton « Lancer une mise à jour complète » de l'admin reste disponible.)

## 7. Sauvegardes BDD

```cron
0 3 * * *  cd /home/USER/commodities-explorer && docker compose -f docker-compose.prod.yml exec -T db pg_dump -U commodities commodities | gzip > /home/USER/backups/db-$(date +\%F).sql.gz
```

## Mettre à jour l'app

```bash
git pull
docker compose -f docker-compose.prod.yml up -d --build
```
Les migrations s'appliquent au démarrage du conteneur `backend`.
