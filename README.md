# Mika · Knowledge Ingestion UI

A Django web interface for building and extending your Mika FAISS knowledge base.
Supports three ingestion sources — website URLs (via Firecrawl), GitHub repositories,
and document files (PDF, Markdown, DOCX) — with live streaming logs and new/append index modes.

---

## Changelog

### Bug fixes
- **AI ignoring ingested data** — The FAISS similarity threshold in `searcher.py` was set to `0.8`
  on an **L2 distance** index (lower = more similar). For `all-MiniLM-L6-v2`, relevant chunks
  typically return distances of `0.3–1.4`, so the old threshold silently dropped *all* results
  and the AI always answered "I don't know." **Fixed: threshold raised to `1.5`.**
- **Chunks stored as plain strings vs dicts** — `ingest_pdf` stored bare strings, but the
  chunker and searcher expected `{"text": ..., "source": ...}` dicts. Now unified across all
  ingestion paths.
- **Chunker had no overlap** — consecutive chunks could cut sentences at boundaries, hurting
  retrieval. **Fixed: 100-character overlap added between chunks.**

### New features
- **Markdown (.md) ingestion** — the file upload pane now accepts `.md` / `.markdown` files.
- **Word document (.docx) ingestion** — requires `python-docx` (added to `requirements.txt`).
- **Source attribution** — every chunk now stores its `source` (filename or URL) for future
  citation / debugging.
- **Unified file endpoint** — `POST /api/ingest/file/` replaces `/api/ingest/pdf/` (old URL
  still works as a backwards-compatible alias).
- **RAG debug logging** — `searcher.py` now logs distances and warns when 0 chunks pass the
  threshold, making future tuning much easier.

---

## Project layout

```
mika_django/
├── manage.py
├── requirements.txt
├── .env.example
│
├── mika_project/          # Django project (settings, root urls)
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
│
├── mika_ingestion/        # The ingestion Django app
│   ├── urls.py            # /  /api/ingest/url|github|pdf/  /api/indexes/
│   ├── views.py           # UI view + SSE API endpoints
│   ├── services.py        # Thin wrappers around your RAG scripts
│   ├── templates/ingestion/index.html
│   └── static/ingestion/
│       ├── css/main.css
│       └── js/main.js
│
├── rag/                   # ← DROP YOUR EXISTING SCRIPTS HERE
│   ├── builder.py
│   ├── git_builder.py
│   ├── chunker.py
│   ├── embedder.py
│   ├── indexer.py
│   ├── crawler.py
│   └── storage.py
│
├── indexes/               # Auto-created — .faiss + .pkl files land here
└── uploads/               # Auto-created — temp PDF storage
```

---

## Setup

```bash
# 1. Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy your RAG scripts into the rag/ folder
cp /path/to/your/scripts/*.py rag/

# 4. Configure environment
cp .env.example .env
# Edit .env — at minimum set DJANGO_SECRET_KEY and FIRECRAWL_API_KEY

# 5. Fix the hardcoded API key in crawler.py
# Replace:  self.client = Firecrawl(api_key='fc-...')
# With:     import os
#           self.client = Firecrawl(api_key=os.environ['FIRECRAWL_API_KEY'])

# 6. Collect static files
python manage.py collectstatic --noinput

# 7. Run the development server
python manage.py runserver
```

Open http://127.0.0.1:8000 in your browser.

---

## API endpoints

| Method | Path | Body / params | Description |
|--------|------|---------------|-------------|
| GET  | `/api/indexes/` | — | List existing index names |
| POST | `/api/ingest/url/` | `{url, index_name, append, crawl_limit}` | Ingest a website |
| POST | `/api/ingest/github/` | `{repo_url, index_name, append, extensions[]}` | Ingest a GitHub repo |
| POST | `/api/ingest/file/` | `multipart: file, index_name, append` | Ingest a PDF, Markdown, or DOCX file |
| POST | `/api/ingest/pdf/` | `multipart: file, index_name, append` | *(alias for `/api/ingest/file/` — kept for backwards compatibility)* |

All three ingest endpoints return **Server-Sent Events** with frames:

```
event: log
data: {"level": "info|warn|ok|err|bold", "msg": "..."}

event: done
data: {"chunks": 412, "vectors": 412, "index_name": "default"}

event: error
data: {"msg": "something went wrong"}
```

---

## Production

```bash
# Use gunicorn instead of runserver
gunicorn mika_project.wsgi:application --workers 2 --bind 0.0.0.0:8000
```

Set `DEBUG=false` and `ALLOWED_HOSTS=yourdomain.com` in `.env`.

Add a reverse proxy (nginx/Caddy) in front for static files and SSL.

---

## Notes

- Ingestion runs **synchronously** in the request thread — for long crawls consider
  moving to Celery + Redis and streaming progress via a task ID.
- The Firecrawl API key is currently hardcoded in `crawler.py`. Move it to the
  `FIRECRAWL_API_KEY` env var (see Setup step 5).
- PDF extraction requires a text layer. Scanned PDFs need OCR (e.g. `pytesseract`).
- DOCX support requires `python-docx` (`pip install python-docx`).
- **Tuning the RAG threshold:** if the bot still answers incorrectly, run the Django shell
  and inspect raw distances:
  ```python
  from rag.searcher import Search
  s = Search("indexes/default.faiss", "indexes/default.pkl")
  # distances[0][0] tells you the closest chunk's L2 distance for your question
  import numpy as np
  q = s.embedder.embedder.encode(["your test question"], convert_to_numpy=True)
  d, i = s.index.search(q, 5)
  print(d)  # if all > 1.5 you need to raise the threshold in searcher.py
  ```

---

## Telegram bot

The bot uses the same FAISS indexes built via the web UI. It talks to Gemini (Google AI Studio) instead of OpenRouter.

### Setup

```bash
# Add these to your .env
TELEGRAM_TOKEN=your-token-from-botfather
GEMINI_API_KEY=your-google-ai-studio-key
GEMINI_MODEL=gemma-4-31b-it      # or any model you have access to
DEFAULT_INDEX=default             # which index the bot queries by default
```

### Running both together

```bash
python run.py
```

This starts Django on `http://localhost:8000` and the Telegram bot in a parallel thread. One `Ctrl+C` stops both.

### Bot commands

| Command | Description |
|---------|-------------|
| `/start` | Greeting + shows available indexes |
| `/indexes` | List all available FAISS indexes |
| `/index <name>` | Switch to a different knowledge index |
| `/clear` | Reset your conversation memory |

### How it works

```
User message (Telegram)
  → RAG: embed question → FAISS search → relevant doc chunks
  → Memory: retrieve past Q&A for this user
  → Prompt = persona + context + memory + question
  → Gemini (streaming internally, assembled before reply)
  → Reply to user (prose + code as separate messages)
  → Save Q&A to user's memory index
```
