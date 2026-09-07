from django.urls import path
from . import views

urlpatterns = [
    path("", views.api_root),
    path("health", views.health),
    path("eta/<str:train_number>", views.eta),
    path("corridor/<path:corridor_name>", views.corridor),
    path("stations/<str:station_code>/departures", views.departures),
    path("events", views.ingest_event),
]
