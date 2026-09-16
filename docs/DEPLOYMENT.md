# Deploying to a server

Two supported ways to run ISP Manager for real:

- **[Option A — Ubuntu with systemd and nginx](#option-a--ubuntu-with-systemd-and-nginx)**
  — the app runs directly on the server. Best for a single VPS.
- **[Option B — Docker Compose](#option-b--docker-compose)** — the app, Postgres
  and Redis run as containers behind nginx.

Both end with the same [scheduled jobs](#scheduled-jobs),
[backups](#backups) and [update routine](#updating).

Before either, have ready:

- A server with **2 GB RAM or more** (1 GB works for a small base).
- A **domain name** pointing at the server, e.g. `isp.example.com`.
- SSH access as a user with `sudo`.

The examples use Ubuntu 24.04, the domain `isp.example.com` and the install
path `/srv/isp-manager`. Change them to suit.

---

## Option A — Ubuntu with systemd and nginx

```
browser ──HTTPS──▶ nginx :443 ──▶ gunicorn 127.0.0.1:8000 ──▶ PostgreSQL
                                                         └──▶ Redis
```

nginx terminates TLS and forwards to gunicorn. Static files are served by the
app itself through WhiteNoise, so nginx needs no static configuration.

### 1. Install system packages

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y git nginx postgresql redis-server certbot python3-certbot-nginx

# Python 3.14 (Ubuntu 24.04 ships an older one)
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt install -y python3.14 python3.14-venv
```

### 2. Create the database

```bash
sudo -u postgres psql <<'SQL'
CREATE USER isp WITH PASSWORD 'change-this-password';
CREATE DATABASE isp OWNER isp;
SQL
```

Use a long random password — `openssl rand -base64 24` makes one.

### 3. Create a system user and get the code

The app runs as its own unprivileged user, never as root.

```bash
sudo adduser --system --group --home /srv/isp-manager isp
sudo -u isp git clone https://github.com/sabbir-mahmud/isp-management-for-reseller.git /srv/isp-manager/app
cd /srv/isp-manager/app
sudo -u isp python3.14 -m venv /srv/isp-manager/venv
sudo -u isp /srv/isp-manager/venv/bin/pip install -r requirements.txt
```

### 4. Configure

```bash
sudo -u isp cp .env.example .env
sudo -u isp chmod 600 .env
sudo -u isp nano .env
```

Set at least:

```dotenv
SECRET_KEY=<output of the command below>
DEBUG=False
ALLOWED_HOSTS=isp.example.com
CSRF_TRUSTED_ORIGINS=https://isp.example.com

DATABASE_URL=postgres://isp:change-this-password@localhost:5432/isp
REDIS_URL=redis://localhost:6379/0

# nginx sets these headers, and nothing else can reach gunicorn.
TRUST_PROXY_HEADERS=True

SITE_NAME=Your ISP name
TIME_ZONE=Asia/Dhaka

# Recommended: move the Django admin off its well-known path.
ADMIN_URL=manage-7f3a/
```

> gunicorn's own settings (`GUNICORN_BIND`, `WEB_CONCURRENCY`) are not read
> from `.env` — only Django's are. They are set in the systemd unit below.

Generate the secret key with:

```bash
/srv/isp-manager/venv/bin/python -c "from django.core.management.utils import get_random_secret_key as g; print(g())"
```

> `.env` holds the database password and the secret key. Keep it `chmod 600`,
> owned by `isp`, and never commit it.

### 5. Prepare the application

```bash
cd /srv/isp-manager/app
sudo -u isp /srv/isp-manager/venv/bin/python manage.py migrate
sudo -u isp /srv/isp-manager/venv/bin/python manage.py collectstatic --noinput
sudo -u isp /srv/isp-manager/venv/bin/python manage.py createsuperuser
sudo -u isp DEBUG=False /srv/isp-manager/venv/bin/python manage.py check --deploy
```

`migrate` also creates the staff roles. The last command audits the security
settings; it should report no issues.

### 6. Run gunicorn under systemd

Create `/etc/systemd/system/isp-manager.service`:

```ini
[Unit]
Description=ISP Manager (gunicorn)
After=network.target postgresql.service redis-server.service
Requires=postgresql.service

[Service]
Type=simple
User=isp
Group=isp
WorkingDirectory=/srv/isp-manager/app
# gunicorn reads these from the process environment, not from .env.
# Localhost only: nginx is the way in.
Environment=GUNICORN_BIND=127.0.0.1:8000
Environment=WEB_CONCURRENCY=3
ExecStart=/srv/isp-manager/venv/bin/gunicorn isp_management.wsgi:application --config gunicorn.conf.py
Restart=on-failure
RestartSec=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/srv/isp-manager

[Install]
WantedBy=multi-user.target
```

Django reads `.env` from the working directory, so the unit does not load it.
`WEB_CONCURRENCY` defaults to two per CPU core plus one; three suits a small
VPS. Start it:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now isp-manager
sudo systemctl status isp-manager
curl -fsS http://127.0.0.1:8000/healthz   # {"status": "ok", "database": true}
```

Logs go to the journal: `journalctl -u isp-manager -f`.

### 7. Put nginx in front

Create `/etc/nginx/sites-available/isp-manager`:

```nginx
server {
    listen 80;
    server_name isp.example.com;

    client_max_body_size 10m;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $remote_addr;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 70s;
    }
}
```

`X-Forwarded-For` is set to the connecting address, not appended to, so a
client cannot forge its own address past the login throttle.

```bash
sudo ln -s /etc/nginx/sites-available/isp-manager /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx
```

### 8. Turn on HTTPS

```bash
sudo certbot --nginx -d isp.example.com --redirect
```

Certbot adds the certificate to the nginx site and renews it automatically.
Open `https://isp.example.com/` and sign in.

With `DEBUG=False` the app already sends HSTS, redirects plain HTTP and marks
cookies secure. HSTS is set for a year — once a browser has seen it, that
domain must keep serving HTTPS.

### 9. Firewall

```bash
sudo ufw allow OpenSSH
sudo ufw allow 'Nginx Full'
sudo ufw enable
```

PostgreSQL, Redis and gunicorn listen on localhost only and stay closed.

---

## Option B — Docker Compose

The repository's `docker-compose.yml` runs Postgres, Redis and the app. On a
server, put nginx (or any TLS proxy) in front of it.

```bash
sudo apt install -y docker.io docker-compose-v2 nginx certbot python3-certbot-nginx
git clone https://github.com/sabbir-mahmud/isp-management-for-reseller.git /srv/isp-manager
cd /srv/isp-manager
cp .env.example .env && chmod 600 .env
```

In `.env`, set `SECRET_KEY` and a strong `POSTGRES_PASSWORD`. Then edit the
`web` service's `environment` in `docker-compose.yml` for your domain:

```yaml
      ALLOWED_HOSTS: isp.example.com
      CSRF_TRUSTED_ORIGINS: https://isp.example.com
      # Keep SECURE_SSL_REDIRECT "False": nginx does the redirect.
```

and bind the port to localhost only, so the app is reached through nginx:

```yaml
    ports:
      - "127.0.0.1:8000:8000"
```

Start it and create an owner:

```bash
sudo docker compose up -d --build
sudo docker compose exec web python manage.py createsuperuser
```

Then follow [step 7](#7-put-nginx-in-front) and [step 8](#8-turn-on-https)
from Option A — the nginx site is identical.

For the scheduled jobs, run the commands inside the container:

```cron
0 1 1 * * cd /srv/isp-manager && docker compose exec -T web python manage.py generate_invoices
0 2 * * * cd /srv/isp-manager && docker compose exec -T web python manage.py refresh_overdue
```

---

## Scheduled jobs

Two jobs keep billing moving. For Option A, edit the `isp` user's crontab:

```bash
sudo crontab -u isp -e
```

```cron
# Raise the month's invoices, on the 1st at 01:00
0 1 1 * * cd /srv/isp-manager/app && /srv/isp-manager/venv/bin/python manage.py generate_invoices >> /srv/isp-manager/cron.log 2>&1

# Flag invoices that have passed their due date, daily at 02:00
0 2 * * * cd /srv/isp-manager/app && /srv/isp-manager/venv/bin/python manage.py refresh_overdue >> /srv/isp-manager/cron.log 2>&1
```

Cron uses the server's clock; set it to your business time zone with
`sudo timedatectl set-timezone Asia/Dhaka`.

- `generate_invoices` is safe to re-run: clients already billed for the month
  are skipped. Preview with `--dry-run`, bill another month with
  `--period 2026-09`.
- It does nothing while **Billing → Settings → Raise invoices automatically**
  is off, unless run with `--force`.

## Backups

The database is everything. Back it up nightly and keep copies off the server.

```bash
sudo install -d -o postgres -g postgres -m 700 /var/backups/isp
sudo -u postgres crontab -e
```

```cron
# Nightly at 03:00, keep 14 days
0 3 * * * pg_dump -Fc isp > /var/backups/isp/isp-$(date +\%F).dump && find /var/backups/isp -name '*.dump' -mtime +14 -delete
```

Copy `/var/backups/isp` elsewhere (another server, object storage) — a backup
on the same disk does not survive the disk.

Restore into an empty database:

```bash
sudo systemctl stop isp-manager
sudo -u postgres pg_restore --clean --if-exists -d isp /var/backups/isp/isp-2026-09-16.dump
sudo systemctl start isp-manager
```

For Docker, dump from the `db` container:
`docker compose exec -T db pg_dump -U isp -Fc isp > isp-$(date +%F).dump`.

## Updating

Option A:

```bash
cd /srv/isp-manager/app
sudo -u isp git pull
sudo -u isp /srv/isp-manager/venv/bin/pip install -r requirements.txt
sudo -u isp /srv/isp-manager/venv/bin/python manage.py migrate
sudo -u isp /srv/isp-manager/venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart isp-manager
```

Option B:

```bash
cd /srv/isp-manager
git pull
sudo docker compose up -d --build
```

Take a backup before any update that includes migrations.

## Checklist

- [ ] `DEBUG=False`, and `manage.py check --deploy` reports no issues
- [ ] `SECRET_KEY` is long, random and only in `.env` (mode 600)
- [ ] `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` name your domain
- [ ] `REDIS_URL` is set (the login throttle needs a shared cache)
- [ ] `TRUST_PROXY_HEADERS=True` only because nginx sets `X-Forwarded-For`
- [ ] `ADMIN_URL` moved off `admin/`
- [ ] HTTPS works and plain HTTP redirects
- [ ] `https://isp.example.com/healthz` returns `"status": "ok"`
- [ ] Both cron jobs installed, server time zone set
- [ ] Nightly backup running, copied off the server, and a restore tested once
