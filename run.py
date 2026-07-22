import os, sys, subprocess, signal, logging
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).parent / ".env")

# Fix SSL cert verification before any network library loads
import certifi, os
os.environ["SSL_CERT_FILE"]      = certifi.where()
os.environ["REQUESTS_CA_BUNDLE"] = certifi.where()

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("run")

required = {"DJANGO_SECRET_KEY": "Django secret key", "TELEGRAM_TOKEN": "Telegram bot token", "GEMINI_API_KEY": "Google AI Studio API key"}
missing = [f"  {var}  ({desc})" for var, desc in required.items() if not os.environ.get(var)]
if missing:
    logger.error("Missing env vars:\n%s", "\n".join(missing)); sys.exit(1)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "mika_project.settings")

host = os.environ.get("DJANGO_HOST", "127.0.0.1")
port = os.environ.get("DJANGO_PORT", "8000")
logger.info("Starting Django on http://%s:%s …", host, port)

django_proc = subprocess.Popen(
    [sys.executable, "manage.py", "runserver", f"{host}:{port}", "--noreload"],
    cwd=Path(__file__).parent,
)

def shutdown(sig, frame):
    logger.info("Shutting down…")
    django_proc.terminate()
    sys.exit(0)

signal.signal(signal.SIGINT, shutdown)
signal.signal(signal.SIGTERM, shutdown)

logger.info("Starting Mika Telegram bot…")
from bot import run_bot
run_bot()