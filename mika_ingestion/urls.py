from django.urls import path
from . import views

app_name = "ingestion"

urlpatterns = [
    path("",                    views.index,            name="index"),
    path("api/indexes/",        views.api_list_indexes, name="api_list_indexes"),
    path("api/ingest/url/",     views.api_ingest_url,   name="api_ingest_url"),
    path("api/ingest/github/",  views.api_ingest_github,name="api_ingest_github"),
    # New unified file endpoint (PDF + MD + DOCX)
    path("api/ingest/file/",    views.api_ingest_file,  name="api_ingest_file"),
    # Legacy PDF endpoint — kept for backwards compatibility
    path("api/ingest/pdf/",     views.api_ingest_pdf,   name="api_ingest_pdf"),
]
