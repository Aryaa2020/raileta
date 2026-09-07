"""Submission-aligned forecast and event services.

The demo deliberately uses synthetic CRIS-shaped events and mock forecasts. The same
response contract is used when RTIS/COA adapters are enabled in production.
"""

import random
import math
from datetime import timedelta
from typing import Any, Dict, List

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import FeedSnapshot, TrainEvent, TrainForecast
from .forecasting import calibrated_window

STATIONS = [
    ("MAS", "MGR Chennai Central"),
    ("AJJ", "Arakkonam Junction"),
    ("KPD", "Katpadi Junction"),
    ("JTJ", "Jolarpettai Junction"),
    ("KPN", "Kuppam"),
    ("BWT", "Bangarapet Junction"),
    ("KJM", "Krishnarajapuram"),
    ("BNC", "Bengaluru Cantonment"),
    ("SBC", "KSR Bengaluru City"),
]
LIVE_TRAIN_SOURCES = {
    "PUBLIC_NTES",
    "PUBLIC_RAILYATRI",
    "SIMULATED_CRIS",
    "CRIS_REST",
    "RTIS",
    "COA",
    "SIMULATED_RTIS",
    "SIMULATED_COA",
}

TRAIN_PROFILES = {
    "12007": {
        "name": "Chennai–Mysuru Shatabdi",
        "class": "Shatabdi",
        "current": "MAS",
        "delay": 8.0,
    },
    "12639": {
        "name": "Brindavan Express",
        "class": "Superfast",
        "current": "KPD",
        "delay": 18.0,
    },
    "12607": {
        "name": "Lalbagh Superfast",
        "class": "Superfast",
        "current": "JTJ",
        "delay": 12.0,
    },
    "22625": {
        "name": "Chennai–Bengaluru Double Decker",
        "class": "AC Chair Car",
        "current": "AJJ",
        "delay": 24.0,
    },
    "12609": {
        "name": "Mysuru Express",
        "class": "Mail/Express",
        "current": "MAS",
        "delay": 6.0,
    },
}


def _configured_snapshot_sources():
    adapter_name = (
        getattr(settings, "RAILETA_DATA_ADAPTER", "simulated").strip().lower()
    )
    if adapter_name in {"simulated", "demo", "fixture"}:
        return {"SIMULATED_CRIS"}
    if adapter_name in {"cris", "cris_rest", "rest"}:
        return {"CRIS_REST"}
    return {"PUBLIC_NTES", "PUBLIC_RAILYATRI"}


def _source_state(train_number: str):
    latest = (
        TrainEvent.objects.filter(train_number=str(train_number), accepted=True)
        .order_by("-event_time")
        .first()
    )
    if latest:
        return latest.source, latest.event_time
    return "PUBLIC_NTES", timezone.now() - timedelta(minutes=2)


def _latest_public_snapshot(train_number: str):
    return (
        FeedSnapshot.objects.filter(
            source__in=_configured_snapshot_sources(),
            payload__train_number=str(train_number),
            error="",
        )
        .order_by("-fetched_at")
        .first()
    )


def _live_snapshot_numbers():
    """Return only trains observed by the collector, never fixture-only trains."""
    allowed = set(getattr(settings, "RAILETA_TRAIN_NUMBERS", ()))
    rows = FeedSnapshot.objects.filter(
        source__in=_configured_snapshot_sources(), error=""
    ).order_by("-fetched_at")
    numbers = []
    seen = set()
    for row in rows:
        number = str((row.payload or {}).get("train_number", ""))
        if number and number in allowed and number not in seen:
            seen.add(number)
            numbers.append(number)
    return numbers


def _profile_for(number: str):
    return TRAIN_PROFILES.get(
        number, {"name": f"Train {number}", "class": "Rail service"}
    )


def _route_station(snapshot, code: str):
    for stop in (snapshot.payload or {}).get("route", []):
        if str(stop.get("station_code", "")).upper() == str(code).upper():
            return stop
    return None


def _route_geometry(snapshot):
    """Return the observed public route geometry for a train snapshot.

    RailYatri's server-rendered route contains sampled coordinates as well as
    the station records. Keeping those points attached to the snapshot makes
    the UI route-specific and auditable; it is not a synthetic line between
    Chennai and Bengaluru.
    """
    if not snapshot:
        return None
    route = (snapshot.payload or {}).get("route", [])
    coordinate_index = {}
    if snapshot.source == "PUBLIC_NTES":
        # NTES supplies the authoritative ordered station list but not a
        # coordinate polyline. Reuse the latest captured RailYatri route
        # coordinates for the same station codes; this is a schematic, not
        # a claim that NTES supplied a live GPS position.
        for coordinate_snapshot in FeedSnapshot.objects.filter(
            source="PUBLIC_RAILYATRI"
        ).order_by("-fetched_at")[:30]:
            for coordinate_row in (coordinate_snapshot.payload or {}).get("route", []):
                code = str(coordinate_row.get("station_code", "")).upper()
                if code in coordinate_index:
                    continue
                try:
                    coordinate_index[code] = (
                        float(coordinate_row["lat"]),
                        float(coordinate_row["lng"]),
                    )
                except (KeyError, TypeError, ValueError):
                    continue
    coordinates = []
    stops = []
    last = None
    for row in route:
        if not isinstance(row, dict):
            continue
        code = str(row.get("station_code", "")).upper()
        try:
            lat = float(row.get("lat"))
            lng = float(row.get("lng"))
        except (TypeError, ValueError):
            lat, lng = coordinate_index.get(code, (None, None))
        if (
            lat is not None
            and lng is not None
            and (
                not math.isfinite(lat)
                or not math.isfinite(lng)
                or not -90 <= lat <= 90
                or not -180 <= lng <= 180
            )
        ):
            lat = lng = None
        if lat is not None and lng is not None:
            point = [round(lng, 6), round(lat, 6)]
            # Public pages sometimes repeat a station coordinate several times.
            if point != last:
                coordinates.append(point)
                last = point
        if code:
            stops.append(
                {
                    "station_code": code,
                    "station_name": row.get("station_name") or code,
                    "stop": bool(row.get("stop", True)),
                    "lat": round(lat, 6) if lat is not None else None,
                    "lng": round(lng, 6) if lng is not None else None,
                    "sequence": row.get("sequence"),
                    "scheduled_arrival": row.get("scheduled_arrival")
                    or row.get("scheduledArrival"),
                    "scheduled_departure": row.get("scheduled_departure")
                    or row.get("scheduledDeparture"),
                }
            )
    if len(coordinates) < 2:
        return None
    coordinate_source = (
        "SIMULATED_ROUTE"
        if snapshot.source == "SIMULATED_CRIS"
        else "PUBLIC_RAILYATRI" if snapshot.source == "PUBLIC_NTES" else snapshot.source
    )
    return {
        "source": snapshot.source,
        "fetched_at": snapshot.fetched_at,
        "coordinates": coordinates,
        "stops": stops,
        "coordinate_source": coordinate_source,
        "geometry_kind": "station_schematic",
    }


def _snapshot_current_station(snapshot):
    status = (snapshot.payload or {}).get("status", {})
    current_code = str(status.get("current_station_code", "")).upper()
    if current_code:
        return current_code
    next_code = str(status.get("next_station_code", "")).upper()
    route = (snapshot.payload or {}).get("route", [])
    if next_code:
        for index, stop in enumerate(route):
            if str(stop.get("station_code", "")).upper() == next_code:
                for previous in reversed(route[:index]):
                    code = str(previous.get("station_code", "")).upper()
                    if code in {station[0] for station in STATIONS} and previous.get(
                        "stop"
                    ):
                        return code
                return "MAS"
    # Structured adapters may persist a route snapshot without duplicating
    # current station state; resolve that state from canonical RTIS/COA events.
    train_number = str((snapshot.payload or {}).get("train_number", ""))
    if train_number:
        state = resolve_train_state(train_number)
        if state and state.station_code:
            return str(state.station_code).upper()
    return None


def _live_delay(number: str, snapshot, current_station: str):
    latest = resolve_train_state(number)
    if latest and isinstance(latest.payload, dict) and latest.payload.get("demo"):
        latest = None
    if (
        latest
        and isinstance(latest.payload, dict)
        and latest.payload.get("delay_minutes") is not None
    ):
        try:
            return (
                round(float(latest.payload["delay_minutes"]), 1),
                latest.source,
                latest.event_time,
            )
        except (TypeError, ValueError):
            pass
    stop = _route_station(snapshot, current_station) if snapshot else None
    if stop:
        for key in (
            "delay_departure",
            "delayDeparture",
            "delay_arrival",
            "delayArrival",
            "delay_minutes",
        ):
            if stop.get(key) is not None:
                try:
                    return (
                        round(float(stop[key]), 1),
                        snapshot.source,
                        snapshot.fetched_at,
                    )
                except (TypeError, ValueError):
                    break
    return (
        None,
        snapshot.source if snapshot else "PUBLIC_RAILYATRI",
        snapshot.fetched_at if snapshot else None,
    )


def _latest_weather():
    rows = TrainEvent.objects.filter(
        event_type="weather_observation",
        station_code__in=[code for code, _ in STATIONS],
        source__in=["PUBLIC_WEATHER_MODEL", "PUBLIC_IMD"],
        accepted=True,
    ).order_by("-event_time")
    latest = {}
    for row in rows:
        if isinstance(row.payload, dict) and row.payload.get("demo"):
            continue
        if row.station_code not in latest:
            latest[row.station_code] = {
                "station_code": row.station_code,
                "event_time": row.event_time,
                "source": row.source,
                "data": row.payload,
            }
    return list(latest.values())


def _event_kind(event: TrainEvent) -> str:
    source = str(event.source or "").upper()
    if "WTT" in source:
        return "WTT"
    if event.event_type == "rtis_position" or "RTIS" in source or "REMMLOT" in source:
        return "RTIS"
    if event.event_type in {"coa_arrival", "coa_departure"} or "COA" in source:
        return "COA"
    if "WTT" in source:
        return "WTT"
    return "OTHER"


def resolve_train_state(train_number: str):
    """Apply RTIS → COA → WTT precedence with a stale-event guard.

    The adapter is deliberately absent from this function: any source that
    emits the canonical event contract can participate in the same state logic.
    """
    from .event_store import MOVEMENT_TYPES

    rows = TrainEvent.objects.filter(
        train_number=str(train_number),
        accepted=True,
        event_type__in=MOVEMENT_TYPES,
        event_time__lte=timezone.now(),
    ).exclude(Q(payload__has_key="demo") & Q(payload__demo=True))
    # Time is the high-water mark. Source priority breaks ties, never overrides
    # a newer observation. Keep the last position when all feeds are stale.
    latest = rows.order_by("-event_time", "-sequence", "-pk").first()
    if not latest:
        return None
    candidates = list(rows.filter(event_time=latest.event_time))
    return min(
        candidates,
        key=lambda event: (
            {"RTIS": 0, "COA": 1, "WTT": 2}.get(_event_kind(event), 3),
            -(event.sequence or 0),
        ),
    )


def state_metadata(train_number, event=None):
    """Freshness/fallback are distinct from the held last-known position."""
    event = event or resolve_train_state(train_number)
    now = timezone.now()
    cutoff = now - timedelta(seconds=settings.RAILETA_EVENT_STALE_SECONDS)
    fallback = "WTT"
    for kind, types in (
        ("RTIS", ("rtis_position",)),
        ("COA", ("coa_arrival", "coa_departure")),
    ):
        if (
            TrainEvent.objects.filter(
                train_number=str(train_number),
                accepted=True,
                event_type__in=types,
                event_time__gte=cutoff,
                event_time__lte=now,
            )
            .exclude(Q(payload__has_key="demo") & Q(payload__demo=True))
            .exclude(source__icontains="WTT")
            .exists()
        ):
            fallback = kind
            break
    return {
        "fallback_kind": fallback,
        "is_stale": event is None or event.event_time < cutoff,
        "position_held": bool(event and event.event_time < cutoff),
        "baseline_available": TrainEvent.objects.filter(
            train_number=str(train_number), accepted=True, source__icontains="WTT"
        ).exists(),
    }


def _event_state(train_number: str, profile: Dict[str, Any], snapshot=None):
    """Return state from the adapter-independent fallback chain."""
    latest = resolve_train_state(train_number)
    if (
        snapshot
        and (latest is None or (latest.source or "").startswith("PUBLIC_"))
        and snapshot.source in {"PUBLIC_NTES", "PUBLIC_RAILYATRI"}
    ):
        return (
            _snapshot_current_station(snapshot),
            None,
            snapshot.fetched_at,
            snapshot.source,
        )
    if not latest:
        if snapshot and snapshot.source in {"PUBLIC_NTES", "PUBLIC_RAILYATRI"}:
            status = (snapshot.payload or {}).get("status", {})
            return (
                _snapshot_current_station(snapshot),
                None,
                snapshot.fetched_at,
                snapshot.source,
            )
        return None, None, None, "WTT"
    delay = latest.payload.get("delay_minutes")
    try:
        delay = float(delay)
    except (TypeError, ValueError):
        delay = None
    return latest.station_code or None, delay, latest.event_time, latest.source


def _reason_codes(
    rng: random.Random, profile: Dict[str, Any], station_name: str
) -> List[Dict[str, Any]]:
    reasons = [
        {
            "category": "congestion",
            "minutes": round(rng.uniform(5, 13), 1),
            "description": f"Heavy traffic ahead at {station_name}",
            "icon": "🚦",
        },
        {
            "category": "weather",
            "minutes": round(rng.uniform(3, 8), 1),
            "description": "Seasonal visibility impact on the section",
            "icon": "🌫",
        },
    ]
    if profile["class"] in {"Mail/Express", "Passenger"} and rng.random() > 0.35:
        reasons.append(
            {
                "category": "precedence",
                "minutes": round(rng.uniform(8, 15), 1),
                "description": "Precedence risk for a higher-priority train",
                "icon": "🔄",
            }
        )
    return reasons[:3]


def forecast_train(train_number: str, persist=False) -> Dict[str, Any]:
    if settings.RAILETA_DATA_ADAPTER == "historical_profiles":
        from .profile_replay import profile_forecast
        return profile_forecast(train_number)
    number = str(train_number)
    if number not in settings.RAILETA_TRAIN_NUMBERS:
        raise LookupError("Train is not in the configured MAS-SBC pilot roster")
    profile = TRAIN_PROFILES.get(
        number,
        {
            "name": f"Demo Express {number}",
            "class": "Mail/Express",
            "current": "MAS",
            "delay": 24.0,
        },
    )
    rng = random.Random(f"raileta-event-demo-{number}")
    live_snapshot = _latest_public_snapshot(number)
    current_station, event_delay, event_time, event_source = _event_state(
        number, profile, live_snapshot
    )
    observed_geometry = _route_geometry(live_snapshot)
    route = (live_snapshot.payload or {}).get("route", []) if live_snapshot else []
    route_stations = [
        (
            str(stop.get("station_code", "")),
            stop.get("station_name") or stop.get("station_code"),
        )
        for stop in route
        if isinstance(stop, dict) and stop.get("station_code")
    ]
    station_index = next(
        (i for i, (code, _) in enumerate(route_stations) if code == current_station), -1
    )
    metadata = state_metadata(number)
    current_status = {
        "train_number": number,
        "train_name": profile["name"],
        "train_class": profile["class"],
        "current_delay_minutes": event_delay,
        "last_reported_station": current_station,
        "last_reported_time": event_time,
        "next_station": (
            route_stations[station_index + 1][0]
            if 0 <= station_index < len(route_stations) - 1
            else ""
        ),
        **metadata,
        "position_mode": (
            (live_snapshot.payload or {}).get("status", {}).get("position_mode")
            if live_snapshot
            else None
        )
        or "station_event",
        "gps_available": bool(
            live_snapshot
            and not (live_snapshot.payload or {})
            .get("status", {})
            .get("gps_unable", True)
        ),
    }
    source, freshness = event_source, event_time
    base = event_time.replace(second=0, microsecond=0) if event_time else None
    upcoming = []
    cumulative = 0
    # ETA values remain the demo prediction layer until labelled historical
    # actuals are available; live station/source state above is never invented.
    rolling_delay = float(event_delay or 0)
    for code, name in (
        route_stations[station_index + 1 :] if station_index >= 0 and base else []
    ):
        cumulative += rng.randint(68, 88)
        scheduled = base + timedelta(minutes=cumulative)
        rolling_delay = max(0.0, rolling_delay + rng.uniform(-3, 5))
        predicted = scheduled + timedelta(minutes=rolling_delay)
        width = rng.randint(9, 14) * (2 if metadata["is_stale"] else 1)
        calibrated = calibrated_window(
            predicted, width, settings.RAILETA_CONFIDENCE_LEVEL
        )
        lower = calibrated.q10
        upper = calibrated.q90
        reasons = _reason_codes(rng, profile, name)
        loop = None
        if any(reason["category"] == "precedence" for reason in reasons):
            loop = {
                "station_code": code,
                "station_name": name,
                "probability": round(rng.uniform(0.62, 0.86), 2),
                "expected_hold_minutes": round(rng.uniform(8, 15), 1),
                "overtaking_train": "12007" if number != "12007" else "12639",
                "overtaking_train_name": (
                    "Chennai–Mysuru Shatabdi"
                    if number != "12007"
                    else "Brindavan Express"
                ),
            }
        row = {
            "station_code": code,
            "station_name": name,
            "scheduled_arrival": scheduled,
            "predicted_arrival": predicted,
            "confidence_lower": lower,
            "confidence_upper": upper,
            "delay_minutes": round(rolling_delay, 1),
            "delay_reasons": reasons,
            "loop_prediction": loop,
            "platform": None,
            "prediction_mode": "mock",
        }
        upcoming.append(row)
        if persist:
            TrainForecast.objects.update_or_create(
                train_number=number,
                station_code=code,
                defaults={
                    "station_name": name,
                    "scheduled_arrival": scheduled,
                    "predicted_arrival": predicted,
                    "confidence_lower": lower,
                    "confidence_upper": upper,
                    "delay_minutes": round(rolling_delay, 1),
                    "source_freshness": freshness,
                    "fallback_source": source,
                    "model_version": settings.RAILETA_MODEL_VERSION,
                    "calibration_level": settings.RAILETA_CONFIDENCE_LEVEL,
                    "reason_codes": reasons,
                },
            )
    return {
        "train_number": number,
        "train_name": profile["name"],
        "train_class": profile["class"],
        "current_status": current_status,
        "upcoming_stations": upcoming,
        "overall_delay_reasons": _reason_codes(rng, profile, "the corridor"),
        "last_updated": freshness,
        "data_freshness": freshness,
        "fallback_source": source,
        **metadata,
        "data_mode": (
            "simulated"
            if source.startswith("SIMULATED")
            else "unavailable" if freshness is None else "observed"
        ),
        "prediction_mode": "mock",
        "calibration_status": "unvalidated_demo_window",
        "model_version": settings.RAILETA_MODEL_VERSION,
        "calibration_level": settings.RAILETA_CONFIDENCE_LEVEL,
        "ntes_comparison": None,
        "weather_observations": _latest_weather(),
        # Observed route geometry is intentionally separate from the mocked
        # ETA output. It is only present when the public page supplied points.
        "route_geometry": observed_geometry,
        "route_stops": (observed_geometry or {}).get("stops", route),
    }


def corridor_status(corridor_name: str) -> Dict[str, Any]:
    if settings.RAILETA_DATA_ADAPTER == "historical_profiles":
        from .profile_replay import profile_corridor
        return profile_corridor()
    if corridor_name.upper() != "MAS-SBC":
        return {
            "corridor_name": corridor_name,
            "total_trains": 0,
            "trains": [],
            "congestion_hotspots": [],
            "timestamp": timezone.now(),
            "data_freshness": None,
        }
    trains = []
    freshness = []
    for number in _live_snapshot_numbers():
        snapshot = _latest_public_snapshot(number)
        if not snapshot:
            continue
        profile = _profile_for(number)
        current_station = _snapshot_current_station(snapshot)
        delay, source, event_time = _live_delay(number, snapshot, current_station)
        status_payload = (snapshot.payload or {}).get("status", {})
        next_station = str(status_payload.get("next_station_code", "")).upper() or None
        if not next_station:
            current_index = next(
                (
                    index
                    for index, (code, _) in enumerate(STATIONS)
                    if code == current_station
                ),
                -1,
            )
            next_station = (
                STATIONS[current_index + 1][0]
                if 0 <= current_index + 1 < len(STATIONS)
                else None
            )
        route_status = (
            status_payload.get("new_message")
            or status_payload.get("title")
            or (
                "Simulated CRIS events"
                if snapshot.source == "SIMULATED_CRIS"
                else "Reported feed events"
            )
        )
        if event_time:
            freshness.append(event_time)
        observed_geometry = _route_geometry(snapshot)
        trains.append(
            {
                "train_number": number,
                "train_name": profile["name"],
                "train_class": profile["class"],
                "current_station": current_station,
                "delay_minutes": delay,
                "next_station": next_station,
                "status": route_status,
                "source": source,
                "position_mode": status_payload.get("position_mode") or "station_event",
                "gps_available": not bool(status_payload.get("gps_unable", True)),
                "last_event_time": event_time,
                "data_freshness": event_time,
                **state_metadata(number),
                "route_geometry": observed_geometry,
            }
        )
    selected_geometry = next(
        (row.get("route_geometry") for row in trains if row.get("route_geometry")), None
    )
    return {
        "corridor_name": "MAS-SBC",
        "total_trains": len(trains),
        "trains": trains,
        "congestion_hotspots": [],
        "weather_observations": _latest_weather(),
        "timestamp": timezone.now(),
        "data_freshness": max(freshness) if freshness else None,
        "route_geometry": selected_geometry,
        "coverage": {
            "observed_train_count": len(trains),
            "configured_train_count": len(
                getattr(settings, "RAILETA_TRAIN_NUMBERS", ())
            ),
            "source_scope": "Configured MAS-SBC adapter roster; not a complete railway timetable",
        },
    }


def station_departures(station_code: str, limit: int = 10) -> Dict[str, Any]:
    if settings.RAILETA_DATA_ADAPTER == "historical_profiles":
        from .profile_replay import profile_departures
        return profile_departures(station_code)
    station_code = station_code.upper()
    departures = []
    for number in _live_snapshot_numbers():
        snapshot = _latest_public_snapshot(number)
        stop = _route_station(snapshot, station_code) if snapshot else None
        if not stop or stop.get("stop") is False:
            continue
        profile = _profile_for(number)
        status_payload = (snapshot.payload or {}).get("status", {})
        destination = status_payload.get("destination") or "SBC"
        scheduled_minutes = stop.get("std_min")
        scheduled_label = _minutes_to_clock(scheduled_minutes)
        if scheduled_label is None:
            scheduled_label = _departure_clock(
                stop.get("scheduled_departure") or stop.get("scheduledDeparture")
            )
        event_rows = TrainEvent.objects.filter(
            train_number=number,
            station_code=station_code,
            accepted=True,
            event_type="coa_departure",
            source__in=LIVE_TRAIN_SOURCES,
        )
        run_id = (snapshot.payload or {}).get("run_id")
        if run_id:
            event_rows = event_rows.filter(payload__run_id=run_id)
        else:
            event_rows = event_rows.filter(
                event_time__gte=timezone.now() - timedelta(hours=24)
            )
        event = event_rows.order_by("-event_time").first()
        if event and isinstance(event.payload, dict) and event.payload.get("demo"):
            event = None
        actual = (
            event.event_time if event and event.event_type == "coa_departure" else None
        )
        delay = None
        for key in (
            "delay_departure",
            "delayDeparture",
            "delay_minutes",
            "delay_arrival",
            "delayArrival",
        ):
            if stop.get(key) is not None:
                try:
                    delay = round(float(stop[key]), 1)
                    break
                except (TypeError, ValueError):
                    pass
        if (
            event
            and isinstance(event.payload, dict)
            and event.payload.get("delay_minutes") is not None
        ):
            try:
                delay = round(float(event.payload["delay_minutes"]), 1)
            except (TypeError, ValueError):
                pass
        status = (
            "Departed" if actual else str(stop.get("status") or "Scheduled").title()
        )
        departures.append(
            {
                "train_number": number,
                "train_name": profile["name"],
                "destination": destination,
                "scheduled_departure": scheduled_label,
                "actual_departure": actual,
                # Kept for the existing display contract: this is the observed
                # departure time when available, otherwise the published schedule.
                "predicted_departure": (
                    timezone.localtime(actual).strftime("%H:%M")
                    if actual
                    else scheduled_label
                ),
                "delay_minutes": delay,
                "platform": str(stop.get("platform_number") or "—"),
                "status": status,
                "source": event.source if event else snapshot.source,
                "data_freshness": snapshot.fetched_at,
            }
        )
    departures.sort(key=lambda row: row["scheduled_departure"] or "99:99")
    return {
        "station_code": station_code,
        "timestamp": timezone.now(),
        "data_freshness": max(
            (row["data_freshness"] for row in departures), default=None
        ),
        "departures": departures[:limit],
    }


def _departure_clock(value):
    from django.utils.dateparse import parse_datetime, parse_time

    if not isinstance(value, str):
        return None
    try:
        instant = parse_datetime(value)
        if instant and timezone.is_aware(instant):
            return timezone.localtime(instant).strftime("%H:%M")
        clock = parse_time(value)
        return clock.strftime("%H:%M") if clock else None
    except ValueError:
        return None


def _minutes_to_clock(value):
    try:
        minutes = int(value) % (24 * 60)
    except (TypeError, ValueError):
        return None
    return f"{minutes // 60:02d}:{minutes % 60:02d}"
