# Mika · EC2 Deployment Guide

## Architecture

```
Internet
   │
   ▼
Nginx (port 80/443)          ← reverse proxy, serves static files
   │
   ▼
Gunicorn (127.0.0.1:8000)    ← Django dashboard  [supervisor: mika-web]
   │
   ├── indexes/               ← FAISS .faiss + .pkl files (shared)
   └── bots.json              ← bot configs (written by dashboard)

Bot processes (one per bot):  [supervisor: mika-bot-<id>]
   bot_runner.py --bot-id a1b2c3d4   ← reads bots.json, runs polling
   bot_runner.py --bot-id e5f6g7h8   ← fully isolated process
   ...
```

**Why this beats PM2 for Python:**
- Each bot is an isolated OS process → no shared asyncio event loop → no thread errors
- Supervisor auto-restarts crashed bots (same as `pm2 --restart-delay`)
- Gunicorn workers handle concurrent dashboard requests without blocking each other
- Nginx buffers are disabled for SSE routes so ingestion logs stream in real time

---

## Quick start

### 1. Provision an EC2 instance
- Ubuntu 22.04 LTS, t3.small (2 vCPU / 2 GB RAM) minimum
- t3.medium recommended if running 3+ bots with large indexes
- Open ports: **22** (SSH), **80** (HTTP), **443** (HTTPS if using SSL)

### 2. Upload the project
```bash
# From your local machine:
scp -r mika/ ubuntu@YOUR-EC2-IP:/home/ubuntu/mika
```

### 3. Run the deploy script
```bash
ssh ubuntu@YOUR-EC2-IP
cd /home/ubuntu/mika
chmod +x deploy/deploy.sh
sudo ./deploy/deploy.sh
```

### 4. Fill in your secrets
```bash
nano /home/ubuntu/mika/.env
# Set DJANGO_SECRET_KEY, GEMINI_API_KEY, ALLOWED_HOSTS
```

### 5. Open the dashboard
```
http://YOUR-EC2-IP
```

### 6. Add bots
1. Go to **Databases** → ingest your data
2. Go to **Bots** → click **New Bot**
3. Fill in: name, Telegram token, knowledge database, model
4. Click **Save**, then click **▶ Start**
5. The dashboard calls `bot_manager.py --sync` automatically

---

## PM2 → Supervisor cheat sheet

| PM2 command | Supervisor equivalent |
|---|---|
| `pm2 list` | `sudo supervisorctl status` |
| `pm2 start app.js` | `sudo supervisorctl start mika-web` |
| `pm2 restart app.js` | `sudo supervisorctl restart mika-web` |
| `pm2 stop app.js` | `sudo supervisorctl stop mika-web` |
| `pm2 logs` | `sudo supervisorctl tail -f mika-web stdout` |
| `pm2 logs --lines 100` | `sudo tail -100 /var/log/mika/web-stdout.log` |
| `pm2 save` | (automatic — supervisor reads conf files) |
| `pm2 startup` | `sudo systemctl enable supervisor` |
| `ecosystem.config.js` | `/etc/supervisor/conf.d/mika.conf` + per-bot files |

---

## Daily operations

### View all process status
```bash
sudo supervisorctl status
```

### Restart the web dashboard (e.g. after a code update)
```bash
sudo supervisorctl restart mika-web
```

### View web logs (live)
```bash
sudo supervisorctl tail -f mika-web stdout
```

### View a specific bot's logs
```bash
sudo tail -f /var/log/mika/bot-a1b2c3d4-stdout.log
```

### Deploy a code update
```bash
cd /home/ubuntu/mika
git pull                          # or scp new files
source venv/bin/activate
pip install -r requirements.txt   # if deps changed
python manage.py collectstatic --noinput
sudo supervisorctl restart mika-web
# Bots pick up code changes on next restart — no action needed unless
# you changed bot_runner.py or main_gemini.py, in which case:
python bot_manager.py --sync
```

### Add a new bot from the CLI (without the dashboard)
```bash
# Edit bots.json manually, then:
python bot_manager.py --sync
```

### Force-restart all bots
```bash
python bot_manager.py --sync
```

---

## HTTPS with Let's Encrypt (recommended for production)

```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d yourdomain.com
# Certbot patches nginx config automatically and sets up auto-renewal
```

---

## Troubleshooting

**Bot not responding after clicking Start**
```bash
sudo supervisorctl status          # check if process is RUNNING
sudo tail -50 /var/log/mika/bot-<id>-stderr.log   # check for errors
```

**"Index not found" error**
The bot's `index_name` in bots.json doesn't match any `.faiss` file in `indexes/`.
Go to Ingest in the dashboard and re-ingest, or edit the bot's database field.

**Ingestion log not streaming**
Make sure nginx has `proxy_buffering off` on the `/api/ingest/` location block.
Check: `sudo nginx -T | grep buffering`

**Permission denied on /var/log/mika**
```bash
sudo chown -R ubuntu:ubuntu /var/log/mika
```

**FAISS thread warnings**
These come from sentence-transformers using OpenMP. Set in `.env`:
```
OMP_NUM_THREADS=1
TOKENIZERS_PARALLELISM=false
```
