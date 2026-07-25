#!/bin/bash
# deploy/deploy.sh
# ─────────────────────────────────────────────────────────────────────────────
# One-shot EC2 setup script for Mika RAG Manager
# Tested on Ubuntu 22.04 LTS (t3.small or larger recommended)
#
# Usage:
#   chmod +x deploy/deploy.sh
#   sudo ./deploy/deploy.sh
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

APP_DIR="/home/ubuntu/mika"
APP_USER="ubuntu"
PYTHON="python3.11"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[INFO]${NC}  $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

# ── 1. System packages ────────────────────────────────────────────────────────
info "Installing system packages…"
apt-get update -qq
apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip \
    nginx \
    supervisor \
    git \
    curl \
    build-essential \
    libssl-dev \
    libffi-dev

# ── 2. Create log directory ───────────────────────────────────────────────────
info "Creating log directory…"
mkdir -p /var/log/mika
chown -R $APP_USER:$APP_USER /var/log/mika

# ── 3. Python virtual environment ─────────────────────────────────────────────
info "Creating virtual environment…"
sudo -u $APP_USER $PYTHON -m venv "$APP_DIR/venv"
VENV_PIP="$APP_DIR/venv/bin/pip"

info "Installing Python dependencies…"
sudo -u $APP_USER "$VENV_PIP" install --upgrade pip -q
sudo -u $APP_USER "$VENV_PIP" install -r "$APP_DIR/requirements.txt" -q
sudo -u $APP_USER "$VENV_PIP" install gunicorn certifi -q

# ── 4. Environment file ───────────────────────────────────────────────────────
if [ ! -f "$APP_DIR/.env" ]; then
    warn ".env not found — creating template at $APP_DIR/.env"
    cat > "$APP_DIR/.env" << 'ENV'
# ── Required ──────────────────────────────────────────────────────────────────
DJANGO_SECRET_KEY=CHANGE_ME_generate_with_python_-c_"import secrets; print(secrets.token_urlsafe(50))"
GEMINI_API_KEY=your-google-ai-studio-key

# ── Django ────────────────────────────────────────────────────────────────────
DJANGO_SETTINGS_MODULE=mika_project.settings
DEBUG=false
ALLOWED_HOSTS=your-ec2-public-ip-or-domain localhost 127.0.0.1

# ── Paths (defaults usually fine) ─────────────────────────────────────────────
INDEX_DIR=/home/ubuntu/mika/indexes
UPLOAD_DIR=/home/ubuntu/mika/uploads
ENV
    chown $APP_USER:$APP_USER "$APP_DIR/.env"
    chmod 600 "$APP_DIR/.env"
    warn "Edit $APP_DIR/.env before starting the app!"
else
    info ".env already exists — skipping"
fi

# ── 5. Django setup ───────────────────────────────────────────────────────────
info "Running Django collectstatic…"
cd "$APP_DIR"
sudo -u $APP_USER bash -c "
    set -a; source .env; set +a
    venv/bin/python manage.py collectstatic --noinput -v 0
"

# ── 6. Nginx ──────────────────────────────────────────────────────────────────
info "Configuring nginx…"
cp "$APP_DIR/deploy/nginx/mika.conf" /etc/nginx/sites-available/mika

# Remove default site if present
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/mika /etc/nginx/sites-enabled/mika

nginx -t || error "Nginx config test failed"
systemctl enable nginx
systemctl restart nginx

# ── 7. Supervisor ─────────────────────────────────────────────────────────────
info "Configuring supervisor…"
cp "$APP_DIR/deploy/supervisor/mika.conf" /etc/supervisor/conf.d/mika.conf

# Inject env vars into supervisor conf from .env
set -a; source "$APP_DIR/.env"; set +a

# Replace placeholder tokens in the supervisor conf
sed -i "s|%(ENV_DJANGO_SECRET_KEY)s|${DJANGO_SECRET_KEY}|g" /etc/supervisor/conf.d/mika.conf
sed -i "s|%(ENV_GEMINI_API_KEY)s|${GEMINI_API_KEY}|g"       /etc/supervisor/conf.d/mika.conf
sed -i "s|%(ENV_ALLOWED_HOSTS)s|${ALLOWED_HOSTS}|g"         /etc/supervisor/conf.d/mika.conf

systemctl enable supervisor
systemctl start supervisor
supervisorctl reread
supervisorctl update
supervisorctl start mika-web

# ── 8. Firewall ───────────────────────────────────────────────────────────────
info "Configuring UFW firewall…"
ufw allow OpenSSH   2>/dev/null || true
ufw allow 'Nginx Full' 2>/dev/null || true
ufw --force enable 2>/dev/null || true

# ── 9. Done ───────────────────────────────────────────────────────────────────
echo ""
info "═══════════════════════════════════════════════"
info " Mika deployment complete!"
info "═══════════════════════════════════════════════"
echo ""
echo "  Dashboard:    http://$(curl -s ifconfig.me 2>/dev/null || echo 'YOUR-IP')"
echo "  Logs:         sudo supervisorctl tail -f mika-web stdout"
echo "  Bot logs:     ls /var/log/mika/"
echo "  Status:       sudo supervisorctl status"
echo ""
warn "Remember to:"
echo "  1. Edit $APP_DIR/.env with your real secrets"
echo "  2. Point your domain at this server's IP (for HTTPS, see deploy/README.md)"
echo "  3. Add bots via the dashboard, then run: python bot_manager.py --sync"
echo ""
