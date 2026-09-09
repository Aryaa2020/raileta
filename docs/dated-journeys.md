# Dated journeys and operational tools

Update: the active demo now uses the trained synthetic corpus described in [corridor-simulation.md](corridor-simulation.md). The original aggregate experiment below remains available for rollback.

## What changed

The existing aggregate-profile experiment and its frozen LightGBM models remain intact. New operational records live in separate tables. A journey is identified by **train number + origin departure date in IST + data mode**, with a UUID used by all its events, stops, and forecasts. No historical average is converted into a journey.

Passenger: expand **Choose a journey date** in the explorer. Select an origin date or include previous runs, then open the complete station timeline or forecast changes for one stop. Controller: expand **Journey history, section conditions & accuracy** below the train overview; choose the relevant tab. Station board: switch from **Departures** to **Expected arrivals**, then choose a station and time window.

The new panels poll every 30 seconds, cancel superseded requests, and explicitly flag failed refreshes. They use the existing solid theme; the controller retains no animations. Tables scroll inside their panels on small screens. Forecast charts include exact values in an expandable table for keyboard/screen-reader access.

## Data boundaries

- `live` means sourced, dated operational records, not proof that a feed is authorized, complete, or accurate. The UI shows source and freshness. The current supplied aggregate dataset cannot populate this mode.
- `simulation` is an isolated namespace. Synthetic runs, section conditions, outcomes and metrics are labelled. Synthetic models can only be activated for simulation.
- Origin and destination timetable fields may be null where appropriate. Intermediate arrival/departure times are explicit timezone-aware datetimes; overnight dates must be supplied, not inferred from the time of day.
- Stop sequence is the identity within a journey; repeated visits to the same station code are not merged.
- Actual arrivals are linked to the same journey and stop. Late reports may supply actual evidence without moving the current position backwards.
- Platforms are copied only from a sourced live event. They are never generated for the simulator or inferred from a timetable or model.
- Unknown windows stay null. **80% is a calibration target, not an established live arrival-window coverage claim.**

## Read-only APIs

All new display endpoints are GET-only. `mode` must be `live` (default) or `simulation`.

| Endpoint | Purpose |
|---|---|
| `/api/v1/journeys?train_number=...&date=YYYY-MM-DD&mode=live` | List up to 200 dated runs; omit date for history |
| `/api/v1/journeys/{uuid}?mode=live` | Complete timetable, reported actuals, held/latest forecasts, destination-delay comparison |
| `/api/v1/journeys/{uuid}/history?sequence=3&mode=live` | Latest 200 issued forecasts in chronological order and eventual actual arrival |
| `/api/v1/stations/{code}/arrivals?hours=3&mode=live` | Expected arrivals in the next 1–24 hours, labelled for stale data |
| `/api/v1/conditions?mode=live` | Supplied active restrictions, blocks and congestion; expiry, severity, source and section geometry |
| `/api/v1/accuracy?mode=live&model_version=...` | Observed point error, baseline comparison, window coverage, sample counts and review status |

An empty conditions list does **not** establish a clear route. Missing geometry is not fabricated. Current condition highlights are not presented as the conditions that existed during a completed historical run.

## Trusted ingestion and Celery

Use the management command for trusted adapter exports:

```powershell
.\venv\Scripts\python.exe manage.py import_journeys path-to-trusted-export.json
```

The JSON has optional `sections`, `journeys`, `events` and `conditions` lists. A journey contains `train_number`, `train_name`, `start_date`, `mode`, `source`, optional numeric `priority`, and ordered `stops`. Each stop supplies `station_code`, `station_name`, `distance_km`, `scheduled_arrival` / `scheduled_departure` (ISO datetimes or null), optional `section_code`, `recovery_minutes`, and `is_junction`. Sections have `code`, `from_station`, `to_station`, `distance_km`, optional `tracks`, `speed_kmph`, `geometry` as `[longitude, latitude]` pairs, `mode` and `source`.

Events supply `journey_id` (unless nested in a new journey), unique `event_id`, `sequence`, `kind` (`arrival`/`departure`), `event_time`, and `source`. Conditions supply `external_id`, `section_code`, `kind` (`restriction`/`block`/`congestion`), numeric `severity` from 0 to 1, `starts_at`, optional `expires_at`, `speed_limit_kmph`, `note`, and `source`. Imports are atomic; timetable rows are not silently overwritten.

Existing canonical adapters may emit `payload.journey_id` and `payload.stop_sequence` on a COA arrival/departure. The train number and station must match the registered journey/stop. Dated HTTP ingestion through `/api/v1/events` additionally requires `RAILETA_JOURNEY_INGEST_TOKEN` and `Authorization: Bearer ...`. Never put that token in frontend configuration. No HTTP write endpoint for operational conditions is exposed.

Accepted dated events and condition changes enqueue `raileta.reforecast_journey` after the transaction commits. A 60-second Celery beat sweep retries durable events after broker failures and checks changed, starting and expired conditions or a new active model. Issuance is idempotent for the same event/condition-state/model. Expiry creates a new issue, not an edit to the old one. Stale station events hold the exact previous forecast rather than moving an ETA forward to look fresh.

Redis, a Celery worker, and beat must be running for live asynchronous reforecasting. API page reads never issue forecasts. The importer can persist data even when the broker is unavailable; the sweep retries it after recovery. No claim is made that a worker is running merely because the web API is running.

## Demonstration

```powershell
.\venv\Scripts\python.exe manage.py simulate_journeys
```

This seeds two same-number dated synthetic services, including one completed journey, append-only forecast revisions and a synthetic restriction. It is an explicit deterministic event replay, not a continuous live feed. It does not replace the configured adapter, load the secondary project's regressor, activate a model, or create real platforms. Re-running does not overwrite an existing dated demo. Existing demo reports naturally become stale; their original timestamps are retained.

To create a fresh pair later without overwriting those runs, use a new ID such as `manage.py simulate_journeys --train-number SIM002`. Conditions and expected-arrivals naturally expire as time passes.

## LightGBM, calibration, replacement and monitoring

`journey_ml.py` trains LightGBM quantile regressors at 0.1, 0.5 and 0.9 on dated arrival-delay outcomes. The feature schema includes remaining distance/stops, scheduled running/halt time, recovery slack, tracks, single-track distance, junctions, priority and supported condition counts/severity/speed limits. Missing infrastructure remains missing, not an invented default. This is a downstream station-delay model, **not a separately trained hop-and-dwell decomposition**; that further decomposition requires suitable hop/dwell labels.

Calibration uses a disjoint chronological journey-date split, CQR residual scores and a finite-sample rank for the 80% target. Train, calibration and test dates are separated 60/20/20. At least 10 dates and 30 samples per split are required. Synthetic and sourced records never train the same release. Train samples use frozen issuance-time features and only predictions issued before actual arrival. Signed TreeSHAP contributions come from the q50 LightGBM model, not random reason codes.

```powershell
.\venv\Scripts\python.exe manage.py journey_model train --mode live --model-version journey-live-v1
.\venv\Scripts\python.exe manage.py journey_model activate --model-version journey-live-v1
```

Training writes a **candidate**, not an active model. Activation requires matching schema, mode, manifest and model checksums, at least 30 held-out samples, MAE no worse than the baseline, and at least 75% measured test coverage against the 80% target. These initial gates are review thresholds, not certification. Model versions are immutable; invalid/incompatible loads fall back to labelled schedule-plus-current-delay with null windows. Model text files are loaded with LightGBM, not unpickled. Each worker checks the shared DB active-version pointer; activation is transactional and isolated by mode.

`RAILETA_JOURNEY_RETRAIN_ENABLED=true` opts into nightly candidate generation where the nightly task is scheduled. Activation remains a separate reviewed command. The aggregate experiment remains frozen by default. Operational accuracy uses the latest pre-arrival issue per journey/stop/lead band/model, reports coverage separately from point error, and includes the baseline and denominator. The panel flags insufficient samples and baseline/coverage threshold breaches for review; it does not auto-deploy replacement models.

There are currently no sourced dated labels sufficient to validate a production journey model. The aggregate model is deliberately incompatible with this schema. Live mode uses baseline estimates with no invented window; the simulation namespace now has the separately trained, explicitly synthetic model documented above.

## Design references

Adapted dated runs, stop ordering, condition and forecast-history concepts from `F:/sah/railway_eta`; did not copy its HistGradientBoosting model, synthetic accuracy claims, or condition-write controls. The local SIH presentation specifies LightGBM, SHAP and time-window calibration; the longer research PDF discusses alternative stacks. Explicit user requirements take precedence: Django/Celery and LightGBM remain in use.

Technical references: [LightGBM Booster / TreeSHAP](https://lightgbm.readthedocs.io/en/latest/pythonapi/lightgbm.Booster.html), [Conformalized Quantile Regression](https://arxiv.org/abs/1905.03222).

## Verification

```powershell
.\venv\Scripts\python.exe manage.py test tests.test_journeys tests.test_django_api tests.test_regressions tests.test_profile_replay
node frontend/tests/dated-journey-browser.cjs
```

Browser tests need all three Vite apps and the API running, seeded simulation records, and Playwright installed or `RAILETA_PLAYWRIGHT_PATH` set. They cover mobile/desktop layouts, mode/date isolation, actual timelines, history charts, conditions, accuracy and arrivals/departure switching. Existing regression suites still apply.
