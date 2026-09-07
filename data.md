# RailETA data and integration plan

## Active dataset mode — 7 September 2026

The approved default is now `historical_profiles`, using `etrain_delays.csv`.
This supersedes the simulation-default statements below for the local demo.
1,900 raw rows become 1,595 unique labelled train/station average-delay profiles.
TRAIN / TEST / DEMO are disjoint by train number (54 / 18 / 18 trains).
TRAIN contains 1,035 profiles, TEST 276, DEMO 284. Only 805 TRAIN profiles fit the
model; another 230 TRAIN profiles calibrate it.

Measured TEST MAE is 24.52 minutes and coverage is 70.29%, **on average delay
profiles**, not individual arrivals. The simple TRAIN-median baseline is better
(23.68 minutes MAE). These results do not establish the submitted <5-minute
ETA target or 80% arrival coverage. See [full methods and results](HISTORICAL_PROFILE_RESULTS.md).

`scraped_at` is page collection time. The data has no run dates, arrival/departure
times, journey event sequences, weather or positions, and no MAS–SBC service
spanning both endpoint codes. It cannot truthfully be replayed as RTIS/COA events.
The demo instead replays original held-out profiles through the actual frozen
model, labels them as aggregates, and does not invoke network collectors.

Still needed from the team: the source/download link and averaging definition;
for actual ETA, dated per-run scheduled/actual ARR/DEP and observation timestamps.
Keep the product architecture below as the future integration specification.

This document is the implementation boundary for SIH26028, based on the submitted
`final final.pdf`. The PDF is the product reference; it is not an instruction to
claim access to CRIS data that we do not yet have.

## Locked prototype scope

- **Pilot corridor:** MGR Chennai Central (`MAS`) → KSR Bengaluru City Junction
  (`SBC`), Southern Railway.
- **Station master:** `MAS`, `AJJ`, `KPD`, `JTJ`, `KPN`, `BWT`, `KJM`, `BNC`,
  `SBC` (Chennai Central, Arakkonam, Katpadi, Jolarpettai, Kuppam, Bangarapet,
  Krishnarajapuram, Bengaluru Cantonment, KSR Bengaluru).
- **Data mode:** structured `SimulatedFeedAdapter` by default for the local
  demo, with a one-line switch to an authorised CRIS REST/JSON adapter. Public
  HTML scraping is disabled and is not the primary architecture.
- **Initial evaluation target:** mean absolute error (MAE) below 5 minutes,
  measured separately by lead-time bucket and reported alongside 80% window
  coverage. This is a target, not a result we can claim before labels exist.

## The current statement

RailETA is an integration-ready, event-driven ETA service. The Django API,
canonical event contract, persisted event/forecast models, fallback handling,
Celery hooks, and three dashboard consumers are in place. The service can run
offline with deterministic fixtures. It is waiting for approved railway feeds
and a small historical labelled dataset before live forecasting can be trained
and enabled.

The production flow will be:

```text
RTIS/REMMLOT, COA, caution orders, ICMS, WTT, weather
        -> source adapters -> canonical events -> validation/deduplication
        -> latest train state + feature tables -> q10/q50/q90 models
        -> 80% calibration + reason codes -> Django API -> NTES/IPIS/controllers
```

## What is implemented now

- Django 5/DRF-compatible API at `/api/v1`.
- `TrainEvent` and `TrainForecast` persistence, event IDs, received times,
  sequence numbers, accepted/rejected state, freshness, fallback source, and
  model version fields.
- `POST /api/v1/events` with duplicate and out-of-order protection.
- `FeedSnapshot` persistence for adapter observations, fetch status,
  parser version, and upstream errors. This is the durable raw-data trail from
  which the local historical dataset can be built.
- Fallback order `RTIS -> COA -> WTT`; stale events cannot move a train
  backwards.
- Deterministic fixtures for the SIH demo and API-compatible passenger,
  controller, and station-display responses.
- Celery tasks for event-triggered reforecasting and scheduled ingestion/retrain
  hooks.

The fixture path is deliberately separate from the live adapter path. It keeps
the demo repeatable; it is not evidence that live CRIS data is connected.

The collector is available as `python manage.py collect_events` (or
`start_data_collector.ps1`). Celery beat schedules the equivalent
`raileta.ingest_data_sources` task every 30 seconds and a separate worker
executes it. The default `SimulatedFeedAdapter` emits structured RTIS-style
position pings, COA station events, and caution-order records for the five
configured pilot trains. The 30-second value is the polling interval, not a
claim that a future railway feed will change on every cycle.

For an authorised deployment, set `RAILETA_DATA_ADAPTER=cris_rest` and
`CRIS_REST_URL` to a structured read-only JSON endpoint. `CrisRestAdapter.poll()`
normalizes its `events`/`data` array into the same canonical contract; no state,
forecast, or dashboard code changes. Public NTES/RailYatri HTML adapters remain
available only behind `RAILETA_ENABLE_PUBLIC_SCRAPING=true` for controlled
experiments and are disabled by default because markup scraping is not the
project's CRIS-network architecture.

## Canonical event contract

Every adapter must emit the same envelope. `payload` may contain source-specific
fields, but the envelope fields are stable and auditable.

```json
{
  "event_id": "public-12007-mas-20260906-060000-001",
  "event_type": "coa_arrival",
  "source": "PUBLIC_RAILYATRI",
  "event_time": "2026-09-05T15:30:00+05:30",
  "received_at": "2026-09-05T15:30:02+05:30",
  "train_number": "12007",
  "station_code": "MAS",
  "section_code": "MAS-AJJ",
  "sequence": 42,
  "payload": {}
}
```

Allowed `event_type` values:

- `rtis_position`: a locomotive/RTIS position update, normally every 30 seconds.
- `coa_arrival`: confirmed station arrival.
- `coa_departure`: confirmed station departure.
- `caution_order`: a speed restriction, block, or operating restriction.
- `weather_observation`: district/station weather observation.

Rules: `event_id` is idempotent; `event_time` is the source occurrence time;
`received_at` is when RailETA saw it; `sequence` is preferred when the source
provides one; raw payloads are retained for audit; invalid events are rejected
with a reason; late events remain stored but cannot regress current state.

## Data required to activate live integration

| Source | Minimum fields needed | Why we need it |
| --- | --- | --- |
| RTIS/REMMLOT | train/loco identity, event time, latitude/longitude or section, speed, source sequence | running position and section speed |
| COA ARR/DEP | train number, station code, event type, actual event time, delay or scheduled reference, controller sequence | authoritative station progress and dwell labels |
| Charting/WTT | train, ordered stations/sections, scheduled arrival/departure, dwell, distance, route/division | baseline ETA and WTT slack |
| Caution orders | order/section ID, effective start/end, restricted speed, affected line, issued time | restrictions and block features |
| ICMS/disruption feed | incident ID, location/section, category, start/end, severity, update time | disruptions and operational context |
| Weather/IMD | observation time, district/station, visibility, fog flag, rainfall, wind, source | seasonal/context features and confidence widening |
| Historical actuals | train/station/section, scheduled and actual arrival/departure, source, at least one representative season | training labels, backtesting, and 80% calibration |

The first pilot does not need every source on day one. COA + WTT + historical
actuals are enough to establish a station-event baseline. RTIS, caution orders,
ICMS, and weather can then be added as independent adapters.

## How data will be obtained

### SIH demo / development

Use captured, replayable JSON/CSV fixtures and the default
`SimulatedFeedAdapter` during development. Configure only endpoint URLs and
non-secret metadata in `.env`; keep credentials outside the repository. The
collector records freshness, source, response time, parser version, and
fixture/live mode. For an authorised deployment, `CrisRestAdapter` consumes a
structured JSON event array through the same interface.

### Weather: what is connected and what is not

There is no weather API key in this project and no weather key was obtained
from anywhere. `IMD_WEATHER_URL` is currently blank, so `ImdWeatherAdapter`
does not claim to ingest live IMD observations. Open-Meteo is now enabled as
`PUBLIC_WEATHER_MODEL`; its current model responses are persisted as
normalized `weather_observation` events and complete raw JSON files. The row
created by `seed_demo` remains a deterministic fixture for offline use.

The honest integration options are:

1. **Preferred railway-aligned path:** configure an approved IMD endpoint after
   its station/district identifier and response schema are confirmed. IMD's
   published API catalogue includes city forecast, current weather, district
   nowcast/rainfall/warnings, station nowcast, RSS, and AWS/ARG endpoints. The
   current IMD API guidance also says the caller's public IP must be whitelisted,
   so this is an access request—not a key we can invent or silently obtain.
2. **Active no-key development provider:** use Open-Meteo's public JSON forecast API,
   labelled `PUBLIC_WEATHER_MODEL`, for station-coordinate context such as
   temperature, humidity, precipitation, visibility, wind, and weather code.
   This is model current data, not an IMD station observation, so it must not be
   presented as live station weather or as a CRIS feed. Its licence requires
   attribution and its free non-commercial allowance is rate-limited.
3. **Offline fallback:** retain the weather fixture and mark the source as
   `DEMO_FIXTURE` when upstream weather is unavailable.

To extract the retained history, run:

```powershell
python manage.py export_data --format jsonl --output data/exports/raileta.jsonl
python manage.py export_data --kind events --format csv --output data/exports/events.csv
```

The export contains both normalized records and pointers to the complete raw
payload files. In Docker, mount the `raileta_rawdata` volume (already present in
`docker-compose.yml`) or replace `RAILETA_RAW_DATA_DIR` with an object-storage
mount/bucket sync path. The collector is deliberately stateless between cycles,
so it can run as a single cloud worker or a scheduled container job.

Weather is a contextual feature that can widen the ETA window; it is never
allowed to create a train movement event. Any future protected provider key
must be injected through a local secret/environment variable and never pasted
into source code, chat, or committed files.

### Railway pilot / production

Obtain read-only access through the Railway/CRIS-approved network path (REST,
JSON, database view, or ESB subscription as authorised). A thin adapter maps the
source schema to the canonical envelope. No dashboard talks directly to CRIS.
The adapter owns authentication, rate limits, retries, clock normalisation,
schema validation, and redaction of sensitive fields.

## Processing and model hand-off

1. Ingest raw messages and write the canonical event plus an audit record.
2. Deduplicate by `event_id`; reject stale or lower-sequence movement events for
   state updates while retaining them for audit.
3. Resolve the latest station/section state using `RTIS -> COA -> WTT`.
4. Build WTT slack, current delay/trend, section speed, congestion, junction
   occupancy, precedence/loop risk, restrictions, and seasonal weather features.
5. Run LightGBM q10/q50/q90 models for runtime, dwell, and loop risk; apply
   monotonic post-processing and conformal calibration targeting 80% coverage.
6. Generate asynchronous SHAP explanations and map the top three contributions
   to controlled reason codes.
7. Persist the forecast with source freshness, fallback source, model version,
   calibration level, and reason codes; publish through the existing API shape.

## Decisions received and remaining inputs

The team has now locked the corridor to MAS → SBC, local-laptop deployment,
indefinite local retention, public web/feed collection for the prototype, and an
initial MAE target below five minutes. The remaining inputs are the artifacts
needed to turn observations into a defensible model:

1. A redacted sample/schema from every public source we keep (including the
   timezone and update cadence) so parsers can be versioned against reality.
2. Historical actual arrival/departure labels. The collector is building raw
   snapshots now; labels still need to be reviewed and marked as actual,
   cancelled, diverted, or missing.
3. The evaluation split: lead-time buckets, minimum sample count, and tolerated
   deviation around the 80% arrival window.
4. Confirmation of which fields may be retained if the prototype is later
   moved beyond the local laptop.

Do not send passwords, tokens, VPN files, or private passenger data in chat or
commit them to this repository. Share a redacted schema first; credentials can
be injected as deployment secrets later.

## Delivery plan after data arrives

1. Confirm schemas and write one adapter per source.
2. Replay a small fixture through validation, deduplication, fallback, and API
   smoke tests.
3. Backfill historical labels and produce a baseline WTT/COA evaluation.
4. Train/version the quantile models and calibrate the arrival window.
5. Run shadow mode beside the existing ETA, monitor freshness/coverage/MAE, and
   only then enable live publishing to NTES/IPIS/controller consumers.

Until those inputs are approved, the honest product statement is: **RailETA is
ready to receive and process the railway events; live accuracy and CRIS
publishing are pending authorised data access and historical labels.**
