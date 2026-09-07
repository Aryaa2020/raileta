# RailETA — SIH demo quick start

RailETA is an event-driven ETA forecasting prototype for coaching trains. The
demo uses persisted station events and deterministic fixtures; it does not claim
GPS navigation or executable dispatch decisions.

## Start the local demo

From PowerShell at the repository root:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
& .\\START_ALL.ps1
```

The script starts the Redis Windows service, Django/DRF, Celery worker and beat,
seeds the demo event set, and launches the three Vite dashboards. Open:

- Passenger: http://127.0.0.1:4173
- Controller: http://127.0.0.1:4174
- Station/IPIS display: http://127.0.0.1:4175
- API health: http://127.0.0.1:8000/api/v1/health

If dependencies are not installed yet, run `pip install -r requirements.txt`
and `pnpm install` (or `npm install`) in each `frontend/*` directory.

## Demo flow

1. Open the controller and select a train from the MAS → SBC corridor track. Progress is
   calculated from confirmed station events, with source/freshness and fallback
   badges.
2. Open the passenger view and search `12007` or `12639`. Show the point ETA,
   lower/upper **80% calibrated arrival window**, and the top reason codes.
3. Open the station display. Use `1`–`5` to switch the seeded station boards.

The seeded trains and events are created by:

```powershell
python manage.py seed_demo
```

## Data and production path

The API accepts canonical events (`rtis_position`, `coa_arrival`,
`coa_departure`, `caution_order`, `weather_observation`) at
`POST /api/v1/events`. Duplicate or out-of-order events are retained for audit
but cannot move a train backwards. Forecasts use the fallback chain
`RTIS → COA → WTT` and expose model version, freshness, calibration level, and
plain-language reasons.

The default collector uses `SimulatedFeedAdapter`, which emits structured
RTIS-style pings, COA station events, and caution orders. Set
`RAILETA_DATA_ADAPTER=cris_rest` and provide `CRIS_REST_URL` only after an
authorised JSON feed is available. Public HTML scraping is disabled by default.
Open-Meteo supplies no-key model weather; `IMD_WEATHER_URL` stays blank until
approved IMD access is available. Docker Compose provides the submitted
PostgreSQL/TimescaleDB, Redis, Django API, Celery worker, and separate beat
services:

```powershell
docker compose up --build
```

The local profile uses SQLite and asynchronous Celery tasks backed by Redis.
For tests only, set `TESTING=true CELERY_TASK_ALWAYS_EAGER=true`.
