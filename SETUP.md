# RailETA setup

## Prerequisites

- Python 3.11+ (the checked-in demo uses `venv`)
- Node.js 18+ and npm/pnpm
- Docker Desktop (optional, for PostgreSQL/TimescaleDB + Redis)

## Local SIH demo

```powershell
python -m venv venv
& .\\venv\\Scripts\\Activate.ps1
pip install -r requirements.txt

# install each UI once
Set-Location frontend/passenger-ui; npm install; Set-Location ../..
Set-Location frontend/controller-dashboard; npm install; Set-Location ../..
Set-Location frontend/station-display; npm install; Set-Location ../..

& .\\START_ALL.ps1
```

The local profile uses SQLite, Redis, and asynchronous Celery worker/beat
processes. It seeds five trains and station events with `python manage.py
seed_demo`. The default `SimulatedFeedAdapter` emits structured events every
30 seconds; no public HTML scraping is enabled.

On Windows, `start_redis.ps1` starts/checks the installed Redis service and
verifies `redis-cli ping`. `start_celery_worker.ps1` and
`start_celery_beat.ps1` are separate processes; neither is embedded in the
Django development server. Docker users can run the equivalent `redis`,
`worker`, and `beat` services with `docker compose up --build`.

Open:

- Passenger UI: http://127.0.0.1:4173
- Controller dashboard: http://127.0.0.1:4174
- Station/IPIS display: http://127.0.0.1:4175
- API health: http://127.0.0.1:8000/api/v1/health

## Submitted service stack

For the Django/DRF + TimescaleDB + Celery/Redis topology:

```powershell
docker compose up --build
```

The compose file starts the API on port 8000, Redis on 6379, and TimescaleDB
on 5432. Set `POSTGRES_HOST`, `POSTGRES_DB`, `POSTGRES_USER`, and
`POSTGRES_PASSWORD` in `.env` when using the containerized database.

## Structured feeds and fixtures

The local collector uses `SimulatedFeedAdapter` for the five MAS→SBC pilot
trains. Open-Meteo weather is enabled by default and requires no key. Set
`OPEN_METEO_ENABLED=false` to disable it. `IMD_WEATHER_URL` can be enabled later
only after IMD access and schema approval. Every normalized event is persisted
with source, event time, received time, sequence/event ID, and payload. Set
`RAILETA_DATA_ADAPTER=cris_rest` with an authorised `CRIS_REST_URL` to swap in a
structured railway JSON adapter without changing the pipeline. Public HTML
scraping is feature-gated and disabled by default.

Celery beat schedules `raileta.ingest_data_sources` every 30 seconds and the
separate Celery worker executes it. For a one-off manual poll, run
`python manage.py collect_events`.

Export the accumulated training/audit data at any time:

```powershell
python manage.py export_data --format jsonl --output data/exports/raileta.jsonl
python manage.py export_data --kind events --format csv --output data/exports/events.csv
```

For a cloud worker, run the Celery worker and beat services as separate
long-lived processes. In Docker Compose the database and raw archive
are named volumes (`raileta_pgdata` and `raileta_rawdata`), so restart cycles do
not discard collected data.

## Verification

```powershell
python manage.py check
python manage.py test tests -v 1
```

The API contract is documented in [API.md](API.md). The three UIs expose only
station-event progress, source freshness/fallback, 80% calibrated windows, and
plain-language forecast reasons; no GPS navigation, public accuracy claims, or
dispatch execution controls are presented.
