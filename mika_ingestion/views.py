"""
views.py
--------
UI view  : index()              – renders the single-page ingestion interface
API views: api_ingest_url()
           api_ingest_github()
           api_ingest_file()    ← replaces api_ingest_pdf; accepts PDF/MD/DOCX
           api_list_indexes()

All API endpoints stream Server-Sent Events (SSE) so the browser log panel
updates in real-time as each pipeline stage completes.
"""

import json
import logging
import uuid
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import services

logger = logging.getLogger(__name__)

# Human-readable labels for accepted file types
ACCEPTED_TYPES_LABEL = "PDF, Markdown (.md), or Word (.docx)"


# ── UI ────────────────────────────────────────────────────────────────────────

def index(request):
    return render(request, "ingestion/index.html")


# ── helpers ───────────────────────────────────────────────────────────────────

def _sse(event: str, data: dict) -> str:
    """Format a single SSE frame."""
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def _stream(generator_fn):
    """Wrap a generator in a StreamingHttpResponse with correct SSE headers."""
    response = StreamingHttpResponse(
        generator_fn(),
        content_type="text/event-stream",
    )
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"   # Disable nginx buffering
    return response


# ── API: list existing indexes ────────────────────────────────────────────────

@require_GET
def api_list_indexes(request):
    return JsonResponse({"indexes": services.list_indexes()})


# ── API: ingest URL ───────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def api_ingest_url(request):
    try:
        body       = json.loads(request.body)
        url        = body.get("url", "").strip()
        index_name = body.get("index_name", "").strip() or "default"
        append     = bool(body.get("append", False))
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    if not url:
        return JsonResponse({"error": "url is required."}, status=400)

    def generate():
        yield _sse("log", {"level": "info",  "msg": f"Starting URL ingestion → {url}"})
        yield _sse("log", {"level": "info",  "msg": f"Mode: {'append' if append else 'new index'} · index: {index_name}"})
        yield _sse("log", {"level": "warn",  "msg": "Crawling — this may take a while…"})
        try:
            result = services.ingest_url(url, index_name, append)
            yield _sse("log",  {"level": "ok", "msg": "Crawl complete"})
            yield _sse("log",  {"level": "ok", "msg": f"Chunked → {result['chunks']} chunks"})
            yield _sse("log",  {"level": "ok", "msg": f"Indexed → {result['vectors']} vectors saved to {index_name}.faiss"})
            yield _sse("done", result)
        except Exception as exc:
            logger.exception("URL ingestion failed")
            yield _sse("error", {"msg": str(exc)})

    return _stream(generate)


# ── API: ingest GitHub ────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def api_ingest_github(request):
    try:
        body       = json.loads(request.body)
        repo_url   = body.get("repo_url", "").strip()
        index_name = body.get("index_name", "").strip() or "default"
        append     = bool(body.get("append", False))
        extensions = body.get("extensions") or [".py", ".js", ".ts", ".md"]
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({"error": "Invalid JSON body."}, status=400)

    if not repo_url:
        return JsonResponse({"error": "repo_url is required."}, status=400)

    def generate():
        yield _sse("log", {"level": "info", "msg": f"Starting GitHub ingestion → {repo_url}"})
        yield _sse("log", {"level": "info", "msg": f"Extensions: {' '.join(extensions)}"})
        yield _sse("log", {"level": "warn", "msg": "Cloning / pulling repo…"})
        try:
            result = services.ingest_github(repo_url, index_name, append, extensions)
            yield _sse("log",  {"level": "ok", "msg": "Repo cloned and files read"})
            yield _sse("log",  {"level": "ok", "msg": f"Chunked → {result['chunks']} chunks"})
            yield _sse("log",  {"level": "ok", "msg": f"Indexed → {result['vectors']} vectors saved to {index_name}.faiss"})
            yield _sse("done", result)
        except Exception as exc:
            logger.exception("GitHub ingestion failed")
            yield _sse("error", {"msg": str(exc)})

    return _stream(generate)


# ── API: ingest file (PDF / Markdown / DOCX) ─────────────────────────────────

@csrf_exempt
@require_POST
def api_ingest_file(request):
    """
    Accept a PDF, Markdown, or DOCX file upload and ingest it into a FAISS index.

    Form fields:
      file        – the uploaded file (required)
      index_name  – target index name (default: "default")
      append      – "true" | "false" (default: "false")
    """
    uploaded = request.FILES.get("file")
    if not uploaded:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    if uploaded.size > settings.MAX_UPLOAD_BYTES:
        mb = settings.MAX_UPLOAD_BYTES // (1024 * 1024)
        return JsonResponse({"error": f"File exceeds {mb} MB limit."}, status=413)

    ext = Path(uploaded.name).suffix.lower()
    if ext not in services.SUPPORTED_EXTENSIONS:
        return JsonResponse(
            {"error": f"Unsupported file type '{ext}'. Accepted: {ACCEPTED_TYPES_LABEL}."},
            status=400,
        )

    index_name = request.POST.get("index_name", "").strip() or "default"
    append     = request.POST.get("append", "false").lower() == "true"

    # Save to temp path, keeping the original extension (extractor needs it)
    tmp_path = settings.UPLOAD_DIR / f"{uuid.uuid4().hex}{ext}"
    with open(tmp_path, "wb") as f:
        for chunk in uploaded.chunks():
            f.write(chunk)

    def generate():
        yield _sse("log", {"level": "info", "msg": f"File received: {uploaded.name} ({uploaded.size // 1024} KB)"})
        yield _sse("log", {"level": "info", "msg": f"Type: {ext.lstrip('.'). upper()} · Mode: {'append' if append else 'new index'} · index: {index_name}"})
        yield _sse("log", {"level": "info", "msg": "Extracting text…"})
        try:
            result = services.ingest_file(
                str(tmp_path), index_name, append, original_name=uploaded.name
            )
            yield _sse("log",  {"level": "ok", "msg": f"Text extracted and chunked → {result['chunks']} chunks"})
            yield _sse("log",  {"level": "ok", "msg": f"Indexed → {result['vectors']} vectors saved to {index_name}.faiss"})
            yield _sse("done", result)
        except Exception as exc:
            logger.exception("File ingestion failed")
            tmp_path.unlink(missing_ok=True)
            yield _sse("error", {"msg": str(exc)})

    return _stream(generate)


# Keep old endpoint alias so any existing integrations still work
@csrf_exempt
@require_POST
def api_ingest_pdf(request):
    return api_ingest_file(request)


# ── API: database stats ───────────────────────────────────────────────────────

@require_GET
def api_db_stats(request):
    """
    Return per-index stats: chunk count, vector count, file size, mtime.
    GET /api/db/stats/
    """
    import pickle, faiss, time
    from pathlib import Path
    from django.conf import settings as s

    results = []
    for faiss_path in sorted(Path(s.INDEX_DIR).glob("*.faiss")):
        name       = faiss_path.stem
        pkl_path   = faiss_path.with_suffix(".pkl")
        size_bytes = faiss_path.stat().st_size + (pkl_path.stat().st_size if pkl_path.exists() else 0)
        mtime      = faiss_path.stat().st_mtime

        vectors = 0
        try:
            idx     = faiss.read_index(str(faiss_path))
            vectors = idx.ntotal
        except Exception:
            pass

        chunks  = 0
        sources = []
        try:
            with open(pkl_path, "rb") as f:
                raw = pickle.load(f)
            chunks = len(raw)
            seen   = set()
            for c in raw:
                src = c.get("source", "") if isinstance(c, dict) else ""
                if src and src not in seen:
                    seen.add(src)
                    sources.append(src)
        except Exception:
            pass

        results.append({
            "name":       name,
            "vectors":    vectors,
            "chunks":     chunks,
            "size_kb":    round(size_bytes / 1024, 1),
            "sources":    sources,
            "updated_at": mtime,
        })

    return JsonResponse({"databases": results})


@csrf_exempt
@require_POST
def api_db_delete(request, name: str):
    """Delete a FAISS index + its pkl. POST /api/db/<name>/delete/"""
    from pathlib import Path
    from django.conf import settings as s

    faiss_path = Path(s.INDEX_DIR) / f"{name}.faiss"
    pkl_path   = Path(s.INDEX_DIR) / f"{name}.pkl"

    if not faiss_path.exists():
        return JsonResponse({"error": f"Index '{name}' not found."}, status=404)

    faiss_path.unlink(missing_ok=True)
    pkl_path.unlink(missing_ok=True)

    return JsonResponse({"deleted": name})


# ── API: bot instances (file-backed, no DB needed) ────────────────────────────

import json as _json
from pathlib import Path as _Path

def _bots_path():
    from django.conf import settings as s
    return _Path(s.INDEX_DIR).parent / "bots.json"

def _load_bots() -> list:
    p = _bots_path()
    if p.exists():
        with open(p) as f:
            return _json.load(f)
    return []

def _save_bots(bots: list):
    with open(_bots_path(), "w") as f:
        _json.dump(bots, f, indent=2)


@require_GET
def api_bot_list(request):
    """GET /api/bots/"""
    return JsonResponse({"bots": _load_bots()})


@csrf_exempt
@require_POST
def api_bot_create(request):
    """POST /api/bots/  body: {name, token, index_name, model, system_prompt}"""
    try:
        body = _json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    import uuid, time
    # Support both index_names (list) and legacy index_name (string)
    raw_indexes = body.get("index_names") or body.get("index_name", "default")
    if isinstance(raw_indexes, str):
        raw_indexes = [raw_indexes]

    bot = {
        "id":            str(uuid.uuid4())[:8],
        "name":          body.get("name", "Unnamed Bot").strip(),
        "token":         body.get("token", "").strip(),
        "index_names":   [i.strip() for i in raw_indexes if i.strip()],
        "model":         body.get("model", "gemma-4-31b-it").strip(),
        "system_prompt": body.get("system_prompt", "").strip(),
        "status":        "stopped",
        "created_at":    time.time(),
        "messages_total": 0,
    }

    if not bot["token"]:
        return JsonResponse({"error": "token is required."}, status=400)

    bots = _load_bots()
    bots.append(bot)
    _save_bots(bots)
    return JsonResponse({"bot": bot}, status=201)


def _sync_bots_async():
    """Call bot_manager.py --sync in a background thread so the API returns fast."""
    import subprocess, sys, threading
    def _run():
        try:
            subprocess.run(
                [sys.executable, "bot_manager.py", "--sync"],
                cwd=_Path(__file__).parent.parent,
                timeout=30,
                capture_output=True,
            )
        except Exception as exc:
            import logging
            logging.getLogger(__name__).warning("bot_manager sync failed: %s", exc)
    threading.Thread(target=_run, daemon=True).start()


@csrf_exempt
@require_POST
def api_bot_update(request, bot_id: str):
    """POST /api/bots/<id>/update/  body: partial fields"""
    try:
        body = _json.loads(request.body)
    except Exception:
        return JsonResponse({"error": "Invalid JSON."}, status=400)

    bots = _load_bots()
    for bot in bots:
        if bot["id"] == bot_id:
            status_changed = "status" in body and body["status"] != bot.get("status")
            for key in ("name", "token", "model", "system_prompt", "status"):
                if key in body:
                    bot[key] = body[key]
            # Handle index_names update (list) or legacy index_name (string)
            if "index_names" in body:
                raw = body["index_names"]
                bot["index_names"] = raw if isinstance(raw, list) else [raw]
            elif "index_name" in body:
                bot["index_names"] = [body["index_name"]]
            _save_bots(bots)
            # If status toggled, sync processes in background
            if status_changed:
                _sync_bots_async()
            return JsonResponse({"bot": bot})

    return JsonResponse({"error": "Bot not found."}, status=404)


@csrf_exempt
@require_POST
def api_bot_delete(request, bot_id: str):
    """POST /api/bots/<id>/delete/"""
    bots = _load_bots()
    new  = [b for b in bots if b["id"] != bot_id]
    if len(new) == len(bots):
        return JsonResponse({"error": "Bot not found."}, status=404)
    _save_bots(new)
    return JsonResponse({"deleted": bot_id})


# ── API: real process status (queries supervisor, not bots.json) ──────────────

@require_GET
def api_bot_process_status(request, bot_id: str):
    """
    GET /api/bots/<id>/status/
    Returns the REAL process state — uses supervisor in production,
    PID file in development. Auto-detected by bot_manager.
    """
    import sys as _sys
    _sys.path.insert(0, str(_Path(__file__).parent.parent))
    import bot_manager as _bm

    bots = _load_bots()
    config_status = "stopped"
    for bot in bots:
        if bot["id"] == bot_id:
            config_status = bot.get("status", "stopped")
            break
    else:
        return JsonResponse({"error": "Bot not found."}, status=404)

    status = _bm.get_status(bot_id)

    def tail(path, n=8):
        try:
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()
            return [l.rstrip() for l in lines[-n:]]
        except FileNotFoundError:
            return []

    log_path = status.get("log_path", "")
    err_path = status.get("err_path", log_path)

    return JsonResponse({
        "bot_id":        bot_id,
        "config_status": config_status,
        "sv_status":     status["sv_status"],
        "pid":           status.get("pid", ""),
        "uptime":        status.get("uptime", ""),
        "stdout_tail":   tail(log_path),
        "stderr_tail":   tail(err_path),
        "log_path":      log_path,
        "err_path":      err_path,
        "mode":          "supervisor" if _bm.has_supervisor() else "subprocess",
    })


# ── API: stream bot log via SSE ───────────────────────────────────────────────

@require_GET
def api_bot_logs(request, bot_id: str):
    """
    GET /api/bots/<id>/logs/?lines=50&stream=1
    Streams the bot's stdout log as SSE.
    ?lines=N   → how many tail lines to send on connect (default 50)
    ?stream=1  → keep connection open and push new lines as they appear
    """
    import time
    from pathlib import Path as _P

    import sys as _sys
    _sys.path.insert(0, str(_P(__file__).parent.parent))
    import bot_manager as _bm
    _status  = _bm.get_status(bot_id)
    log_path = _P(_status.get("log_path", f"/var/log/mika/bot-{bot_id}-stdout.log"))
    err_path = _P(_status.get("err_path", str(log_path)))
    n_lines  = int(request.GET.get("lines", 50))
    streaming = request.GET.get("stream", "0") == "1"

    def read_tail(path, n):
        try:
            with open(path, "r", errors="replace") as f:
                lines = f.readlines()
            return [l.rstrip() for l in lines[-n:]]
        except FileNotFoundError:
            return []

    def generate():
        # Send initial tail
        lines = read_tail(log_path, n_lines)
        if not lines:
            yield f"data: {_json.dumps({'line': '(no log output yet)', 'src': 'stdout'})}\n\n"
        for line in lines:
            yield f"data: {_json.dumps({'line': line, 'src': 'stdout'})}\n\n"

        err_lines = read_tail(err_path, 10)
        for line in err_lines:
            if line.strip():
                yield f"data: {_json.dumps({'line': line, 'src': 'stderr'})}\n\n"

        if not streaming:
            return

        # Keep streaming new lines
        try:
            with open(log_path, "r", errors="replace") as f:
                f.seek(0, 2)   # seek to end
                while True:
                    line = f.readline()
                    if line:
                        yield f"data: {_json.dumps({'line': line.rstrip(), 'src': 'stdout'})}\n\n"
                    else:
                        time.sleep(0.5)
                        yield ": ping\n\n"   # keep-alive
        except FileNotFoundError:
            yield f"data: {_json.dumps({'line': 'Log file not found.', 'src': 'stderr'})}\n\n"
        except GeneratorExit:
            pass

    response = StreamingHttpResponse(generate(), content_type="text/event-stream")
    response["Cache-Control"]    = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
