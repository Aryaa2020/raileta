# etrain aggregate-delay experiment

## What is implemented

The active input is `etrain_delays.csv`, replacing the previous Kaggle arrival
CSV experiment. The old CSV and generated artifacts are retained but are not
loaded, scored, or mixed into this demo. Nothing was deleted from the local DB.

This file is **not a database of dated train runs**. Each row is a train/station
average-delay profile with delay-category percentages. `scraped_at` means page
collection time, never arrival or departure time. Source URLs request `d=1y`,
but exact averaging dates, per-profile journey counts, and upstream provenance
are not independently verified. No external site was fetched for this work.

There are no schedules, dated actual arrivals, coordinates, movement sequences,
or weather records. No service in this export has both MAS and SBC/BNC/YPR.
Consequently this is an aggregate-delay model demonstration, **not** validated
MAS–SBC ETA prediction. The supplied source is unchanged.

## Cleaning and locked splits

Input: 1,900 rows, 90 distinct train numbers, 480 station codes.

- Keep the latest capture per train/station without considering its target:
  71 older duplicate profiles excluded; 1,829 unique profiles remain.
- Exclude 234 unique profiles with missing/invalid average-delay targets. Do
  not turn absent labels into zero or impute them from delay percentages.
- Result: 1,595 usable profiles. The manifest records every excluded CSV line.

| Split | Train numbers | Usable profiles | Share of usable profiles |
| --- | ---: | ---: | ---: |
| TRAIN | 54 | 1,035 | 64.89% |
| TEST | 18 | 276 | 17.30% |
| LIVE-DEMO | 18 | 284 | 17.81% |

The split is 60/20/20 **by train number**, with seed 2026 fixed before fitting.
Row shares differ because trains have different numbers of station profiles.
This preserves substantial training data while leaving 18 completely unseen
train groups for each independent evaluation and demonstration split.
Every train is exclusive to one split. TRAIN is split further by train number:
43 trains / 805 profiles fit the models; 11 trains / 230 profiles calibrate
intervals. Neither TEST nor LIVE-DEMO participates in fitting or calibration.

## Model and measured TEST result

LightGBM quantile models: q10, q50, q90. Fixed 150 boosting rounds, depth 4,
12 leaves, learning rate 0.04. No TEST-based tuning or early stopping.
Category vocabularies come only from fitting rows. Features are station code,
service category extracted from the recorded train name, and whether the
station name includes a junction designation. Unknown categories remain unknown.

Train numbers, record IDs, capture times, actual average delay and every
delay-percentage column are excluded from features. Percentage columns describe
the same outcomes as the target and would make an apparent forecasting result
misleading. Raw columns remain preserved for provenance.

Sort quantiles to prevent crossing. Calibrate using the finite-sample CQR
order statistic of TRAIN-calibration residuals only, targeting 80%. The interval
expansion is 5.2312759801 minutes on each side. Correlated stations within a train
mean pooled calibration does not guarantee coverage for unseen trains.

| TEST measure | Observed result |
| --- | ---: |
| MAE on average station delays | 24.521288 minutes |
| Empirical interval coverage | 70.289855% (194 / 276 profiles) |
| Mean interval width | 50.419272 minutes |
| TRAIN-median baseline MAE | 23.677536 minutes |

The 80% coverage target was **not met**. The LightGBM point forecast did **not**
beat the simple baseline. These are genuine aggregate-profile metrics, not
individual-run MAE or arrival-window coverage. No accuracy improvement is claimed.

SHAP TreeExplainer explains the model supplying the sorted median, with three
controlled reason codes. Signed contributions plus the base value reconcile to
the prediction. These are model associations, not proven operational causes.

Frozen model: `profile-lgbm-17856fece628-a02a76ce`.
Dataset SHA-256 and model checksum, split membership, fit/calibration membership,
parameters, exclusions, and metrics are in
`data/models/etrain-profiles-v1/manifest.json`.
`test_predictions.json` contains every TEST target, prediction, error, bounds,
and coverage indicator so the reported result can be recomputed independently.

## Demo pipeline and truthful API/UI

`HistoricalProfileReplayAdapter` yields held-out aggregate records. It does not
implement a fake RTIS/COA event: aggregate averages cannot truthfully satisfy that
contract. The canonical Event schema remains unchanged. The existing ingestion
task selects this profile-specific path before calling movement/weather adapters.

The worker scores one profile through the frozen model approximately every
15 seconds. A durable cursor survives restarts and stops after all 284 profiles.
Trains are interleaved for a usable roster; this ordering is **not** a train route
or original journey chronology. Both original capture time and replay time are
preserved. Each prediction and its source record are retained in the local DB.
Atomic cursor advancement prevents duplicate task delivery from skipping rows.
No automatic retraining consumes demo labels.

Passenger/controller panels show recorded versus predicted **average** delay,
profile error, the calibrated interval for the average, signed SHAP, and frozen
TEST metrics. They say held-out historical aggregate profiles, not live train
runs. No route position, weather, scheduled arrival or departure is invented.
The station display honestly reports that departure data is unavailable.
Old simulated events remain stored but cannot override the active profile APIs.

## Run locally

```dotenv
RAILETA_DATA_ADAPTER=historical_profiles
RAILETA_HISTORICAL_MODEL_DIR=data/models/etrain-profiles-v1
RAILETA_COLLECTOR_INTERVAL_SECONDS=15
RAILETA_REPLAY_INTERVAL_SECONDS=15
OPEN_METEO_ENABLED=false
RAILETA_ENABLE_PUBLIC_SCRAPING=false
CELERY_TASK_ALWAYS_EAGER=false
```

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py replay_profiles
# Explicitly start another pass; prior generations are retained:
.\venv\Scripts\python.exe manage.py replay_profiles --reset
```

Use the existing separate Redis, Celery worker and beat starters. Runtime eager
execution remains test-only. Redis binding, NTES/CRIS collectors and the old
LightGBM experiment are not modified for network access.

The frozen models are already trained. To reproduce into a **new** directory:

```powershell
.\venv\Scripts\python.exe manage.py train_profiles --dataset etrain_delays.csv --output data/models/etrain-reproduction
.\venv\Scripts\python.exe manage.py test tests
node frontend/tests/historical-replay-smoke.mjs
```

Do not pick whichever reproduction gets the best TEST result; that would turn
TEST into a development set. The command refuses to overwrite frozen outputs.

Docker Compose selects the same offline profile mode. The build includes only
the active model directory from `data/models`; the PostgreSQL volume retains
replay state. Docker is not installed on this laptop, so container startup has
not been verified here. The local SQLite/Redis/worker/beat path is exercised.

## What data is still needed for the submitted ETA goal

A larger count of aggregate profiles does not replace journey-level evidence.
For actual ETA training/evaluation/replay, obtain dated per-run per-station rows:
train number, journey/run ID, station code, scheduled and actual ARR/DEP timestamps
with timezone, original observation/received timestamps, and a reliable timetable.
Then join permissible weather/caution/congestion observations as known at each
forecast cutoff. The CSV's averages can be historical priors only after verifying
their averaging window ends before the target run, to avoid future leakage.

Please supply the dataset/source link and averaging definitions if available.
No new website scraper or live network collector was enabled for this experiment.

## Files changed for the new input

- `raileta_api/profile_model.py`: parsing, audit, grouped splits, frozen quantile
  fitting/calibration, real TEST metrics, SHAP and artifact loading.
- `raileta_api/profile_replay.py`: offline timed profiles, per-record scoring,
  idempotent storage and truthful aggregate API responses.
- `raileta_api/management/commands/train_profiles.py`, `replay_profiles.py`:
  reproducible training and replay status/reset controls.
- `raileta_api/models.py`, migrations `0005` and `0006`: durable replay cursor and
  prediction history; aggregate records intentionally have no movement event.
- `raileta_api/tasks.py`, `ingestion.py`: route the default to offline profile
  processing and prevent weather/public collection in that mode.
- `raileta_api/services.py`, `views.py`: serve stored model scores, profile roster,
  empty departure board and health with real metrics.
- `django_service/settings.py`, `.env`, `.env.example`, `docker-compose.yml`,
  `.dockerignore`, `Dockerfile`: offline defaults, timing, frozen artifact path
  and container runtime dependency.
- Passenger `App.jsx`, `HistoricalReplayDetail.jsx`; controller `App.jsx`,
  `CorridorMap.jsx`, `HistoricalReplayPanel.jsx`; station `App.jsx`, `Header.jsx`:
  aggregate-specific displays and removal of unsupported movement wording.
- `tests/test_profile_replay.py`, `tests/test_django_api.py` and
  `frontend/tests/historical-replay-smoke.mjs`: ML/replay/contract tests and
  explicit legacy simulation test settings.
- `README.md`, `data.md`, this report: current scope, results and remaining data.

Earlier interrupted arrival-CSV work remains inactive and is superseded by this
report. It is not evidence for the new model's accuracy.

## Verification completed

- 37 Django tests passed: parsing, duplicate handling, split isolation, no target
  leakage, TRAIN-only calibration, frozen TEST residuals, SHAP, replay persistence,
  source isolation and no network calls in profile mode.
- All 284 held-out DEMO profiles scored successfully through the frozen model,
  with ordered quantiles and additive SHAP explanations.
- All three Vite production builds passed; 37 UI render-contract assertions passed.
- Browser search/selection passed against the running API in passenger and
  controller dashboards; the station unavailable-data state passed. No browser
  exceptions occurred. Screenshots were inspected; a locked-scroll dimming bug
  was corrected and checked at full opacity.
- Separate Celery worker and beat are running; `inspect ping` returns `pong`.
  Consecutive persisted replay intervals observed: 14.941, 15.048, 15.062 and
  15.007 seconds. Public collection is disabled in the active mode.
- Local dashboards are served at ports 4173, 4174 and 4175; API at 8000.
