# RailETA API

Base URL: `http://localhost:8000/api/v1`

The Django/DRF-compatible service keeps the original dashboard response shapes while adding event freshness and model metadata. The demo uses SQLite automatically; Docker Compose uses PostgreSQL/TimescaleDB and Redis.

## Endpoints

### `GET /health`

Returns service, model, freshness, accepted-event status, and integration mode.

The response includes `data_mode`, `integration_status`, `configured_sources`,
`collector_interval_seconds`, `live_position_mode`, and
`last_adapter_fetch`, and `raw_payload_retention`. Open-Meteo appears as `PUBLIC_WEATHER_MODEL` when
enabled; this is model weather, not an IMD observation. `live_position_mode` is
`station_event` for the demo/structured adapter: polling every 30 seconds does
not create a continuous GPS position.

Example:

```json
{
  "status": "healthy",
  "version": "2.0.0",
  "data_mode": "public_adapters",
  "integration_status": "ready_for_feed_configuration",
  "configured_sources": ["SIMULATED_CRIS", "PUBLIC_WEATHER_MODEL"],
  "raw_payload_retention": true,
  "fallback_chain": ["RTIS", "COA", "WTT"]
}
```

### `GET /eta/{train_number}`

Returns the train identity, last accepted station event, upcoming station predictions, 80% calibrated lower/upper window, delay reasons, source freshness, fallback source, model version, and calibration level.

Example:

```json
{
  "train_number": "12007",
  "train_name": "Chennai–Mysuru Shatabdi",
  "train_class": "Shatabdi",
  "current_status": {
    "last_reported_station": "MAS",
    "next_station": "AJJ",
    "current_delay_minutes": 22.4
  },
  "upcoming_stations": [
    {
      "station_code": "AJJ",
      "predicted_arrival": "2026-09-05T15:56:00+05:30",
      "confidence_lower": "2026-09-05T15:44:00+05:30",
      "confidence_upper": "2026-09-05T16:08:00+05:30",
      "delay_minutes": 24.2,
      "delay_reasons": []
    }
  ],
  "data_freshness": "2026-09-05T15:28:00+05:30",
  "fallback_source": "PUBLIC_NTES",
  "model_version": "demo-event-v1",
  "calibration_level": 0.8
}
```

When the latest public snapshot contains coordinates, the ETA response also
contains `route_geometry` and `route_stops`. These are the selected train's
observed public route samples and station records; the ETA fields beside them
remain the demo prediction layer until labelled historical data is available.

### `GET /corridor/{corridor_name}`

Returns all observed trains in the configured MAS-SBC adapter roster,
current station-event placement, feed freshness, and route-specific geometry.
`route_geometry.coordinates` are `[longitude, latitude]` track samples from the
configured adapter (the simulator uses its route fixture); `route_geometry.stops`
contains the ordered station records. They are route geometry, not a live train
position and not GPS positions inferred by RailETA. The response also includes a
`coverage` object so the UI does not claim that a five-train configured roster is
the complete timetable.

### `GET /stations/{station_code}/departures?limit=10`

Returns the IPIS-style departure board feed with scheduled and predicted departure, platform, delay, source, and freshness.

### `POST /events`

Normalizes and stores a canonical event. Supported `event_type` values:

- `rtis_position`
- `coa_arrival`
- `coa_departure`
- `caution_order`
- `weather_observation`

Request:

```json
{
  "event_id": "public-12007-mas-202609060600-001",
  "event_type": "coa_departure",
  "source": "PUBLIC_RAILYATRI",
  "event_time": "2026-09-05T15:30:00+05:30",
  "train_number": "12007",
  "station_code": "MAS",
  "sequence": 1,
  "payload": {"delay_minutes": 24}
}
```

Duplicate `event_id` values are ignored. Older or lower-sequence movement events are stored but marked `accepted: false`. Accepted train events trigger a Celery reforecast task.

## Fallback and freshness

Forecast state follows `RTIS → COA → WTT`. A stale or out-of-order event cannot move a train backwards. Every forecast exposes the source used, event freshness, model version, and calibration level.

## Demo setup

```powershell
python manage.py migrate
python manage.py seed_demo
python -m uvicorn django_service.asgi:application --reload --port 8000
```

The default `SimulatedFeedAdapter` needs no external feed. Set
`RAILETA_DATA_ADAPTER=cris_rest` and `CRIS_REST_URL` for an authorised JSON
source. Public HTML adapters are feature-gated and disabled by default.
