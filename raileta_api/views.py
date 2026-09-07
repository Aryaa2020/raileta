import json
from datetime import datetime

from django.conf import settings
from django.http import JsonResponse
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .contracts import CanonicalEvent
from .models import FeedSnapshot, TrainEvent
from .services import corridor_status, forecast_train, station_departures


def api_root(request):
    return JsonResponse({
        "name": "RailETA API",
        "version": "2.0.0",
        "description": "Integration-ready event-driven ETA forecasting for coaching trains",
        "integration_status": "awaiting approved railway feeds and historical labels",
        "endpoints": ["/health", "/eta/{train_number}", "/corridor/{corridor_name}", "/stations/{station_code}/departures", "/events"],
    })


@require_http_methods(["GET"])
def health(request):
    if settings.RAILETA_DATA_ADAPTER == "historical_profiles":
        from .profile_replay import profile_health
        return JsonResponse(profile_health())
    latest = TrainEvent.objects.filter(accepted=True, event_type__in=("rtis_position", "coa_arrival", "coa_departure")).order_by("-event_time").first()
    adapter_name = getattr(settings, "RAILETA_DATA_ADAPTER", "simulated").lower()
    train_source = "SIMULATED_CRIS" if adapter_name in {"simulated", "demo", "fixture"} else "CRIS_REST" if adapter_name in {"cris", "cris_rest", "rest"} else "PUBLIC_SCRAPING"
    configured_sources = [train_source]
    if settings.IMD_WEATHER_URL:
        configured_sources.append("IMD_WEATHER")
    if getattr(settings, "OPEN_METEO_ENABLED", False) and getattr(settings, "OPEN_METEO_URL", ""):
        configured_sources.append("PUBLIC_WEATHER_MODEL")
    latest_snapshot = FeedSnapshot.objects.order_by("-fetched_at").first()
    return JsonResponse({
        "status": "healthy" if latest and (timezone.now() - latest.event_time).total_seconds() <= settings.RAILETA_EVENT_STALE_SECONDS else "degraded",
        "version": "2.0.0",
        "model_status": "mock_predictions_not_trained",
        "data_mode": "simulated_adapter" if train_source == "SIMULATED_CRIS" else "structured_adapters" if train_source == "CRIS_REST" else "public_scraping" if train_source == "PUBLIC_SCRAPING" else "demo_fixtures",
        "integration_status": "simulated_adapter_active" if train_source == "SIMULATED_CRIS" else "ready_for_feed_configuration",
        "configured_sources": configured_sources,
        "collector_interval_seconds": getattr(settings, "RAILETA_COLLECTOR_INTERVAL_SECONDS", 30),
        "live_position_mode": "station_event",
        "live_position_note": "The configured adapter is polled at this interval; station-event mode does not imply continuous GPS.",
        "last_adapter_fetch": latest_snapshot.fetched_at if latest_snapshot else None,
        "last_public_fetch": latest_snapshot.fetched_at if latest_snapshot else None,
        "public_fetch_errors": FeedSnapshot.objects.filter(source__in=configured_sources).exclude(error="").count(),
        "last_model_update": None,
        "data_freshness": latest.event_time if latest else None,
        "accepted_events": TrainEvent.objects.filter(accepted=True).count(),
        "fallback_chain": ["RTIS", "COA", "WTT"],
        "raw_payload_retention": bool(getattr(settings, "RAILETA_STORE_RAW_PAYLOADS", False)),
    })


@require_http_methods(["GET"])
def eta(request, train_number):
    try:
        return JsonResponse(forecast_train(train_number))
    except LookupError as exc:
        return JsonResponse({"detail": str(exc)}, status=404)


@require_http_methods(["GET"])
def corridor(request, corridor_name):
    return JsonResponse(corridor_status(corridor_name))


@require_http_methods(["GET"])
def departures(request, station_code):
    try:
        limit = min(50, max(1, int(request.GET.get("limit", 10))))
    except ValueError:
        limit = 10
    return JsonResponse(station_departures(station_code, limit))


@csrf_exempt
@require_http_methods(["POST"])
def ingest_event(request):
    try:
        body = json.loads(request.body or "{}")
        if not isinstance(body, dict):
            raise ValueError("The request body must be a JSON object")
        event_time = parse_datetime(body.get("event_time", ""))
        if event_time is None:
            raise ValueError("event_time must be ISO-8601")
        received_at = parse_datetime(body.get("received_at", "")) or timezone.now()
        if timezone.is_naive(received_at):
            received_at = timezone.make_aware(received_at)
        event = CanonicalEvent(
            event_id=str(body.get("event_id", "")),
            event_type=str(body.get("event_type", "")),
            source=str(body.get("source", "")),
            event_time=event_time,
            received_at=received_at,
            train_number=str(body.get("train_number", "")),
            station_code=str(body.get("station_code", "")),
            section_code=str(body.get("section_code", "")),
            sequence=body.get("sequence"),
            payload=body.get("payload", {}),
        ).validate()
    except (ValueError, TypeError, json.JSONDecodeError) as exc:
        return JsonResponse({"detail": str(exc), "type": "ValidationError"}, status=400)

    from .event_store import store_event, MOVEMENT_TYPES
    record, created = store_event(event)
    if not created:
        return JsonResponse({"event_id": event.event_id, "accepted": False, "deduplicated": True})
    queued = None
    if record.accepted and event.train_number and event.event_type in MOVEMENT_TYPES:
        from .tasks import reforecast_train
        from kombu.exceptions import OperationalError
        try:
            reforecast_train.delay(event.train_number)
            queued = True
        except OperationalError:
            # The event is durable even if the broker is down. Report the
            # partial success, rather than falsely reporting an ingestion 500.
            queued = False
    return JsonResponse({"event_id": record.event_id, "accepted": record.accepted, "deduplicated": False, "forecast_queued": queued}, status=201)
