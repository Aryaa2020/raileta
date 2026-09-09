from django.urls import path
from . import views
from . import journey_views

urlpatterns = [
    path('journeys', journey_views.journeys),
    path('journeys/<uuid:journey_id>', journey_views.journey_detail),
    path('journeys/<uuid:journey_id>/history', journey_views.history),
    path('conditions', journey_views.conditions),
    path('accuracy', journey_views.metrics),
    path('stations/<str:station_code>/arrivals', journey_views.arrivals),
    path("", views.api_root),
    path("health", views.health),
    path("eta/<str:train_number>", views.eta),
    path("corridor/<path:corridor_name>", views.corridor),
    path("stations/<str:station_code>/departures", views.departures),
    path("events", views.ingest_event),
]
