# RailETA

Team members: start with [TEAM_WORKFLOW.md](TEAM_WORKFLOW.md) for cloning,
configuration, version checkpoints, and collaboration. See
[CHANGELOG.md](CHANGELOG.md) for saved milestones. The current offline demo setup
in [HISTORICAL_PROFILE_RESULTS.md](HISTORICAL_PROFILE_RESULTS.md) takes precedence
over the legacy integration examples below.

**Current demo (7 September 2026):** offline held-out aggregate-delay profiles
from `etrain_delays.csv`, scored with trained LightGBM and SHAP. These are
station averages, not live runs or arrival forecasts. TEST MAE: **24.52 min**;
coverage: **70.29%** (80% target not met). See
[the reproducible experiment and demo instructions](HISTORICAL_PROFILE_RESULTS.md).
The original event-driven product architecture below remains a future integration
path, not a description of this dataset's capabilities.

Submission-aligned event-driven ETA forecasting for Indian Railways coaching trains.

RailETA combines structured station movement events, timetable slack, congestion,
precedence risk, caution orders, and seasonal context to produce a point ETA, an
80% calibrated arrival window, and plain-language reason codes. The local demo
now uses the aggregate-profile replay described above; the legacy CRIS-shaped
simulator and an authorised CRIS REST adapter can still be selected
without changing downstream layers.

The backend is integration-ready rather than pretending to have CRIS access: the
live railway feeds and historical labelled runs are the remaining inputs needed
to train and enable production forecasting. See [data.md](data.md) for the data
contract, acquisition plan, and the exact information still needed from the
team.

## Current product surfaces

- Passenger UI: train search, MAS → SBC station-event route progress, ETA windows, and delay reasons.
- Station display: IPIS-style departure board for station staff.
- Controller dashboard: corridor view, event-derived progress, source freshness, and prediction factors.

The existing dark purple liquid-glass visual system is intentionally retained. UI changes are limited to submission-aligned labels and data-quality indicators.

## Architecture

```
SimulatedFeedAdapter (demo)  CRIS RTIS / COA / ICMS (authorised)
          |                                 |
          +------- DataSourceAdapter -------+
                           |
             Canonical event contract
                           |
              Django REST API + PostgreSQL
                           |
          Celery / Redis event processing
                           |
        LightGBM q10/q50/q90 + calibration
                           |
              React passenger / IPIS / controller UIs
```

## Backend setup

The submission-aligned entrypoint is Django 5 + Django REST Framework. SQLite is used automatically for local demo mode; Docker Compose provides PostgreSQL/TimescaleDB and Redis.

```powershell
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo
python -m uvicorn django_service.asgi:application --reload --port 8000
# In another terminal, collect public MAS→SBC observations continuously:
python manage.py collect_events
```

For the full service topology:

```powershell
docker compose up --build
```

## API compatibility endpoints

Base URL: `http://localhost:8000/api/v1`

- `GET /health`
- `GET /eta/{train_number}`
- `GET /corridor/{corridor_name}` (demo corridor: `MAS-SBC`)
- `GET /stations/{station_code}/departures?limit=10`
- `POST /events` for canonical event ingestion

The event endpoint accepts `rtis_position`, `coa_arrival`, `coa_departure`, `caution_order`, and `weather_observation` events. Duplicate IDs are ignored, older movement events are marked unaccepted, and accepted train events trigger a reforecast task.

## Demo data

`python manage.py seed_demo` creates deterministic station-event records for the Chennai–Bengaluru pilot trains `12007`, `12639`, `12607`, `22625`, and `12609`, plus a sample weather observation. The default `SimulatedFeedAdapter` then emits structured RTIS-style pings, COA events, and caution orders every 30 seconds. Forecasts remain repeatable across refreshes and carry source freshness, fallback source, model version, and calibration level. The sample weather row is fixture data, not a live observation.

`RAILETA_DATA_ADAPTER=simulated` is the default. Use
`RAILETA_DATA_ADAPTER=cris_rest` with an authorised `CRIS_REST_URL` to consume
structured railway JSON. Open-Meteo is enabled by default as the no-key,
model-weather provider and is labelled `PUBLIC_WEATHER_MODEL`; it is not an
IMD observation. Snapshots and normalized events are retained under the local
data store. Export the history with `python manage.py export_data`; see
`data.md` for the source and licensing boundaries.

The local collector uses the structured `SimulatedFeedAdapter` by default and
stores observations indefinitely. Set `RAILETA_DATA_ADAPTER=cris_rest` and
`CRIS_REST_URL` to swap in an authorised CRIS JSON endpoint without changing
the state, forecast, or API layers. Public NTES/RailYatri HTML scraping is
feature-gated with `RAILETA_ENABLE_PUBLIC_SCRAPING=false` and is not the default.
The current five-number roster is a demo configuration, not a complete
timetable; replace `RAILETA_TRAIN_NUMBERS` with an authorized roster before
claiming full corridor coverage. Run
`start_data_collector.ps1` or use the `collector` service in Docker Compose.

## Frontend commands

Each app is a standalone React/Vite project:

```powershell
cd frontend/passenger-ui; pnpm install; pnpm run dev
cd frontend/station-display; pnpm install; pnpm run dev
cd frontend/controller-dashboard; pnpm install; pnpm run dev
```

The Windows helpers are also available: `start_backend.ps1`, `start_passenger_ui.ps1`, `start_station_display.ps1`, `start_controller_dashboard.ps1`, and `START_ALL.ps1`.

## Forecasting contract

- q10, q50, and q90 quantiles are post-processed to prevent crossing.
- The displayed arrival window is calibrated to 80% coverage.
- Top-three delay factors use controlled reason codes for congestion, weather, precedence, and carried delay.
- Progress is based on the last accepted station event; no GPS navigation is implied in the UI.

## Production path

Replace the public adapters with read-only CRIS/RailTel adapters for RTIS/REMMLOT, COA, caution orders, and ICMS. Publish forecasts through the CRIS ESB to NTES, IPIS, and downstream passenger channels. Run nightly retraining, weekly drift checks, model versioning, and lead-time accuracy monitoring.

## License

MIT License.
