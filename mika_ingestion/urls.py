from django.urls import path
from . import views

app_name = "ingestion"

urlpatterns = [
    # ── UI ──────────────────────────────────────────────────────────────────
    path("",                         views.index,             name="index"),

    # ── Indexes ──────────────────────────────────────────────────────────────
    path("api/indexes/",             views.api_list_indexes,  name="api_list_indexes"),

    # ── Ingestion ─────────────────────────────────────────────────────────────
    path("api/ingest/url/",          views.api_ingest_url,    name="api_ingest_url"),
    path("api/ingest/github/",       views.api_ingest_github, name="api_ingest_github"),
    path("api/ingest/file/",         views.api_ingest_file,   name="api_ingest_file"),
    path("api/ingest/pdf/",          views.api_ingest_pdf,    name="api_ingest_pdf"),

    # ── Database management ────────────────────────────────────────────────────
    path("api/db/stats/",            views.api_db_stats,      name="api_db_stats"),
    path("api/db/<str:name>/delete/",views.api_db_delete,     name="api_db_delete"),

    # ── Bot management ────────────────────────────────────────────────────────
    path("api/bots/",                          views.api_bot_list,          name="api_bot_list"),
    path("api/bots/create/",                   views.api_bot_create,        name="api_bot_create"),
    path("api/bots/<str:bot_id>/update/",      views.api_bot_update,        name="api_bot_update"),
    path("api/bots/<str:bot_id>/delete/",      views.api_bot_delete,        name="api_bot_delete"),
    # Real process status from supervisor (not bots.json)
    path("api/bots/<str:bot_id>/status/",      views.api_bot_process_status, name="api_bot_process_status"),
    # Tail the bot's log file — SSE stream
    path("api/bots/<str:bot_id>/logs/",        views.api_bot_logs,           name="api_bot_logs"),
]
