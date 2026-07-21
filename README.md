# Mika · Knowledge Ingestion UI

A Django web interface for building and extending your Mika FAISS knowledge base.
Supports three ingestion sources — website URLs (via Firecrawl), GitHub repositories,
and PDF documents — with live streaming logs and new/append index modes.

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
| POST | `/api/ingest/pdf/` | `multipart: file, index_name, append` | Ingest a PDF |

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
