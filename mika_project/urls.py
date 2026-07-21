from django.urls import path, include

urlpatterns = [
    path("", include("mika_ingestion.urls")),
]
