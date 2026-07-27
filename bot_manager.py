"""
bot_manager.py
--------------
Manages bot processes in both dev and production environments.

In PRODUCTION (supervisor installed):
  Writes per-bot .conf files to /etc/supervisor/conf.d/ and uses
  supervisorctl to start/stop/status each process.

In DEVELOPMENT (no supervisor):
  Spawns bot_runner.py directly as a subprocess and tracks PIDs
  in a local pids.json file next to bots.json.

Auto-detects which mode to use. Same API either way.

Usage:
    python bot_manager.py --sync          # start/stop to match bots.json
    python bot_manager.py --status        # show process states
    python bot_manager.py --start <id>
    python bot_manager.py --stop  <id>
"""

import argparse
import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import textwrap
import time
from pathlib import Path

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("bot_manager")

# ── Paths ─────────────────────────────────────────────────────────────────────
BASE_DIR       = Path(__file__).parent
VENV_PYTHON    = BASE_DIR / "venv" / "bin" / "python"
SUPERVISOR_DIR = Path("/etc/supervisor/conf.d")
LOG_DIR        = Path("/var/log/mika")
ENV_FILE       = BASE_DIR / ".env"

def _index_dir() -> Path:
    """
    Resolve INDEX_DIR at call time, not import time.
    When called from Django, settings are already loaded and take precedence.
    Falls back to env var, then to <project>/indexes.
    """
    try:
        from django.conf import settings
        return Path(settings.INDEX_DIR)
    except Exception:
        return Path(os.environ.get("INDEX_DIR", str(BASE_DIR / "indexes")))


def _bots_json() -> Path:
    return _index_dir().parent / "bots.json"


def _pids_file() -> Path:
    return _index_dir().parent / "pids.json"


# Keep module-level names for CLI usage (resolved once at import for CLI only)
BOTS_JSON = BASE_DIR / "bots.json"   # overridden at runtime via _bots_json()
PIDS_FILE = BASE_DIR / "pids.json"   # overridden at runtime via _pids_file()


# ── Environment detection ─────────────────────────────────────────────────────

def has_supervisor() -> bool:
    return shutil.which("supervisorctl") is not None


def _python() -> str:
    return str(VENV_PYTHON) if VENV_PYTHON.exists() else sys.executable


def _prog_name(bot_id: str) -> str:
    return f"mika-bot-{bot_id}"


# ── bots.json helpers ─────────────────────────────────────────────────────────

def load_bots() -> list[dict]:
    path = _bots_json()
    if not path.exists():
        return []
    with open(path) as f:
        return json.load(f)


# ── Dev mode: PID file ────────────────────────────────────────────────────────

def _load_pids() -> dict:
    path = _pids_file()
    if path.exists():
        with open(path) as f:
            try:
                return json.load(f)
            except Exception:
                return {}
    return {}


def _save_pids(pids: dict):
    path = _pids_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(pids, f, indent=2)


def _is_running(pid: int) -> bool:
    """Check if a PID is alive."""
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


def _dev_log_path(bot_id: str) -> Path:
    log_dir = _index_dir().parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir / f"bot-{bot_id}.log"


def dev_start(bot_id: str) -> int | None:
    """Spawn bot_runner.py as a subprocess. Returns the PID."""
    log_path = _dev_log_path(bot_id)
    log_file = open(log_path, "a")

    # Build environment: start from current process (Django already loaded .env),
    # then overlay the .env file for any vars that weren't exported.
    env = os.environ.copy()
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k = k.strip()
                    v = v.strip().strip('"').strip("'")
                    # Only set if not already present (os.environ wins)
                    env.setdefault(k, v)

    # Ensure critical vars are always present
    must_have = ["GEMINI_API_KEY", "DJANGO_SETTINGS_MODULE", "INDEX_DIR"]
    missing = [k for k in must_have if not env.get(k)]
    if missing:
        logger.error(
            "Cannot start bot %s — missing env vars: %s. "
            "Check your .env file or export them before starting Django.",
            bot_id, missing,
        )
        return None

    # Always tell bot_runner where the indexes live
    env["INDEX_DIR"] = str(_index_dir())
    env["DJANGO_SETTINGS_MODULE"] = env.get(
        "DJANGO_SETTINGS_MODULE", "mika_project.settings"
    )

    proc = subprocess.Popen(
        [_python(), str(BASE_DIR / "bot_runner.py"), "--bot-id", bot_id],
        cwd=str(BASE_DIR),
        env=env,
        stdout=log_file,
        stderr=subprocess.STDOUT,
        start_new_session=True,   # detach — survives terminal / gunicorn restart
    )

    # Give the process 1 second to fail fast (bad token, missing index, etc.)
    import time
    time.sleep(1.0)
    if proc.poll() is not None:
        logger.error(
            "Bot %s (PID %d) exited immediately (code %d). "
            "Check the log: %s",
            bot_id, proc.pid, proc.returncode, log_path,
        )
        return None

    pids = _load_pids()
    pids[bot_id] = proc.pid
    _save_pids(pids)

    logger.info(
        "Started bot %s as PID %d  log=%s",
        bot_id, proc.pid, log_path,
    )
    return proc.pid


def dev_stop(bot_id: str):
    """Send SIGTERM to a bot process."""
    pids = _load_pids()
    pid  = pids.get(bot_id)
    if not pid:
        logger.warning("No PID recorded for bot %s", bot_id)
        return
    try:
        os.kill(pid, signal.SIGTERM)
        # Wait up to 5s for clean exit
        for _ in range(10):
            if not _is_running(pid):
                break
            time.sleep(0.5)
        if _is_running(pid):
            os.kill(pid, signal.SIGKILL)
        logger.info("Stopped bot %s (PID %d)", bot_id, pid)
    except ProcessLookupError:
        logger.info("Bot %s (PID %d) was already gone", bot_id, pid)
    finally:
        pids.pop(bot_id, None)
        _save_pids(pids)


def dev_status(bot_id: str) -> dict:
    """Return process status for dev mode."""
    pids    = _load_pids()
    pid     = pids.get(bot_id)
    log_path = _dev_log_path(bot_id)

    if pid and _is_running(pid):
        return {"sv_status": "RUNNING", "pid": str(pid), "uptime": "", "log_path": str(log_path), "err_path": str(log_path)}
    elif pid:
        # PID recorded but process is dead
        pids.pop(bot_id, None)
        _save_pids(pids)
        return {"sv_status": "EXITED", "pid": str(pid), "uptime": "", "log_path": str(log_path), "err_path": str(log_path)}
    else:
        return {"sv_status": "STOPPED", "pid": "", "uptime": "", "log_path": str(log_path), "err_path": str(log_path)}


# ── Production mode: supervisor ───────────────────────────────────────────────

def _env_string() -> str:
    env_vars = {}
    if ENV_FILE.exists():
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    env_vars[k.strip()] = v.strip().strip('"').strip("'")

    required = ["DJANGO_SECRET_KEY", "GEMINI_API_KEY", "DJANGO_SETTINGS_MODULE",
                "INDEX_DIR", "UPLOAD_DIR", "ALLOWED_HOSTS"]
    parts = []
    for key in required:
        val = env_vars.get(key) or os.environ.get(key, "")
        if val:
            parts.append(f'{key}="{val}"')
    try:
        import certifi
        parts.append(f'SSL_CERT_FILE="{certifi.where()}"')
    except ImportError:
        pass
    return ",".join(parts)


def _write_supervisor_conf(bot: dict):
    bot_id  = bot["id"]
    prog    = _prog_name(bot_id)
    conf    = SUPERVISOR_DIR / f"{prog}.conf"
    log_out = LOG_DIR / f"bot-{bot_id}-stdout.log"
    log_err = LOG_DIR / f"bot-{bot_id}-stderr.log"
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    content = textwrap.dedent(f"""\
        ; Auto-generated by bot_manager.py — do not edit manually
        ; Bot: {bot['name']} (id={bot_id})
        [program:{prog}]
        command={_python()} {BASE_DIR}/bot_runner.py --bot-id {bot_id}
        directory={BASE_DIR}
        user={os.environ.get('USER', 'ubuntu')}
        environment={_env_string()}
        autostart=true
        autorestart=true
        startretries=5
        stopasgroup=true
        killasgroup=true
        stdout_logfile={log_out}
        stderr_logfile={log_err}
        stdout_logfile_maxbytes=10MB
        stderr_logfile_maxbytes=10MB
        stdout_logfile_backups=3
        stderr_logfile_backups=3
    """)
    conf.write_text(content)
    logger.info("Wrote %s", conf)


def _rm_supervisor_conf(bot_id: str):
    conf = SUPERVISOR_DIR / f"{_prog_name(bot_id)}.conf"
    if conf.exists():
        conf.unlink()


def _supervisorctl(*args: str) -> tuple[int, str]:
    result = subprocess.run(["supervisorctl"] + list(args), capture_output=True, text=True)
    return result.returncode, (result.stdout + result.stderr).strip()


def _reload_supervisor():
    for cmd in ("reread", "update"):
        rc, out = _supervisorctl(cmd)
        logger.info("supervisorctl %s: %s", cmd, out)


def prod_start(bot: dict):
    _write_supervisor_conf(bot)
    _reload_supervisor()
    rc, out = _supervisorctl("start", _prog_name(bot["id"]))
    logger.info("start %s: %s", bot["id"], out)


def prod_stop(bot_id: str):
    rc, out = _supervisorctl("stop", _prog_name(bot_id))
    logger.info("stop %s: %s", bot_id, out)
    _rm_supervisor_conf(bot_id)
    _reload_supervisor()


def prod_status(bot_id: str) -> dict:
    prog = _prog_name(bot_id)
    rc, raw = _supervisorctl("status", prog)
    parts = raw.split()
    sv_status = parts[1].upper() if len(parts) > 1 else "UNKNOWN"
    uptime    = " ".join(parts[3:]).replace(",", "") if len(parts) > 3 else ""
    pid       = parts[2].replace("pid", "").replace(",", "").strip() if len(parts) > 2 else ""
    log_out   = str(LOG_DIR / f"bot-{bot_id}-stdout.log")
    log_err   = str(LOG_DIR / f"bot-{bot_id}-stderr.log")
    return {"sv_status": sv_status, "pid": pid, "uptime": uptime,
            "log_path": log_out, "err_path": log_err}


# ── Unified API (auto-detects mode) ──────────────────────────────────────────

def start_bot(bot: dict):
    if has_supervisor():
        prod_start(bot)
    else:
        dev_start(bot["id"])


def stop_bot(bot_id: str):
    if has_supervisor():
        prod_stop(bot_id)
    else:
        dev_stop(bot_id)


def get_status(bot_id: str) -> dict:
    if has_supervisor():
        return prod_status(bot_id)
    else:
        return dev_status(bot_id)


# ── CLI commands ──────────────────────────────────────────────────────────────

def cmd_sync():
    bots = load_bots()
    mode = "production (supervisor)" if has_supervisor() else "development (subprocess)"
    logger.info("Syncing %d bots in %s mode", len(bots), mode)

    for bot in bots:
        bot_id  = bot["id"]
        desired = bot.get("status", "stopped")
        current = get_status(bot_id)["sv_status"]

        if desired == "running" and current != "RUNNING":
            logger.info("Starting bot %s (%s)", bot["name"], bot_id)
            start_bot(bot)
        elif desired != "running" and current == "RUNNING":
            logger.info("Stopping bot %s (%s)", bot["name"], bot_id)
            stop_bot(bot_id)
        else:
            logger.info("Bot %s already in desired state (%s)", bot["name"], current)


def cmd_status():
    bots = load_bots()
    mode = "supervisor" if has_supervisor() else "subprocess"
    print(f"\nMode: {mode}\n")
    print(f"{'ID':<10} {'Name':<20} {'Config':<10} {'Process'}")
    print("─" * 60)
    for bot in bots:
        st = get_status(bot["id"])
        print(f"{bot['id']:<10} {bot['name']:<20} {bot.get('status','?'):<10} {st['sv_status']}")
    print()


def main():
    parser = argparse.ArgumentParser(description="Mika bot process manager")
    group  = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--sync",   action="store_true")
    group.add_argument("--status", action="store_true")
    group.add_argument("--start",  metavar="BOT_ID")
    group.add_argument("--stop",   metavar="BOT_ID")
    args = parser.parse_args()

    if args.sync:
        cmd_sync()
    elif args.status:
        cmd_status()
    elif args.start:
        bots = load_bots()
        bot  = next((b for b in bots if b["id"] == args.start), None)
        if not bot:
            logger.error("Bot %s not found", args.start)
            sys.exit(1)
        start_bot(bot)
    elif args.stop:
        stop_bot(args.stop)


if __name__ == "__main__":
    main()
