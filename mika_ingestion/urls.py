from django.urls import path
from . import views

urlpatterns = [
    # UI
    path("", views.index, name="index"),

    # API endpoints called by the frontend via fetch()
    path("api/ingest/url/",    views.api_ingest_url,    name="api_ingest_url"),
    path("api/ingest/github/", views.api_ingest_github, name="api_ingest_github"),
    path("api/ingest/pdf/",    views.api_ingest_pdf,    name="api_ingest_pdf"),
    path("api/indexes/",       views.api_list_indexes,  name="api_list_indexes"),
]
