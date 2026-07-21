"""
views.py
--------
UI view  : index()            – renders the single-page ingestion interface
API views: api_ingest_url()
           api_ingest_github()
           api_ingest_pdf()
           api_list_indexes()

All API endpoints stream Server-Sent Events (SSE) so the browser log panel
updates in real-time as each pipeline stage completes.
"""

import json
import logging
import time
import uuid
from pathlib import Path

from django.conf import settings
from django.http import JsonResponse, StreamingHttpResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_POST

from . import services

logger = logging.getLogger(__name__)


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
            yield _sse("log",    {"level": "ok",   "msg": f"Crawl complete"})
            yield _sse("log",    {"level": "ok",   "msg": f"Chunked → {result['chunks']} chunks"})
            yield _sse("log",    {"level": "ok",   "msg": f"Indexed → {result['vectors']} vectors saved to {index_name}.faiss"})
            yield _sse("done",   result)
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
            yield _sse("log",  {"level": "ok",  "msg": f"Repo cloned and files read"})
            yield _sse("log",  {"level": "ok",  "msg": f"Chunked → {result['chunks']} chunks"})
            yield _sse("log",  {"level": "ok",  "msg": f"Indexed → {result['vectors']} vectors saved to {index_name}.faiss"})
            yield _sse("done", result)
        except Exception as exc:
            logger.exception("GitHub ingestion failed")
            yield _sse("error", {"msg": str(exc)})

    return _stream(generate)


# ── API: ingest PDF ───────────────────────────────────────────────────────────

@csrf_exempt
@require_POST
def api_ingest_pdf(request):
    pdf_file = request.FILES.get("file")
    if not pdf_file:
        return JsonResponse({"error": "No file uploaded."}, status=400)

    if pdf_file.size > settings.MAX_UPLOAD_BYTES:
        return JsonResponse({"error": "File exceeds 50 MB limit."}, status=413)

    if not pdf_file.name.lower().endswith(".pdf"):
        return JsonResponse({"error": "Only PDF files are accepted."}, status=400)

    index_name = request.POST.get("index_name", "").strip() or "default"
    append     = request.POST.get("append", "false").lower() == "true"

    # Save upload to temp path
    tmp_path = settings.UPLOAD_DIR / f"{uuid.uuid4().hex}.pdf"
    with open(tmp_path, "wb") as f:
        for chunk in pdf_file.chunks():
            f.write(chunk)

    def generate():
        yield _sse("log", {"level": "info", "msg": f"PDF received: {pdf_file.name} ({pdf_file.size // 1024} KB)"})
        yield _sse("log", {"level": "info", "msg": "Extracting text…"})
        try:
            result = services.ingest_pdf(str(tmp_path), index_name, append)
            yield _sse("log",  {"level": "ok",  "msg": f"Text extracted and chunked → {result['chunks']} chunks"})
            yield _sse("log",  {"level": "ok",  "msg": f"Indexed → {result['vectors']} vectors saved to {index_name}.faiss"})
            yield _sse("done", result)
        except Exception as exc:
            logger.exception("PDF ingestion failed")
            # Clean up if service didn't
            tmp_path.unlink(missing_ok=True)
            yield _sse("error", {"msg": str(exc)})

    return _stream(generate)
