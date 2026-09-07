# RailETA bug audit - 6 September 2026

Scope: fix faults in existing functionality; do not implement new product features without approval. Proposal checked against `C:\Users\aryaa\Downloads\final final.pdf`, especially pages 2-4 (structured CRIS feeds, event processing, 80% coverage target, fallback and shadow rollout). No changes to the submitted PDF.

## Corrections made

- Tests cannot publish to the laptop's Redis: test mode forces eager execution and in-memory broker/result settings, regardless of runtime `.env`.
- Worker and HTTP ingestion now share validation, deduplication and per-stream ordering. RTIS sequence numbers no longer reject unrelated COA events. Duplicate IDs use the database uniqueness constraint; each polling batch queues at most one forecast per changed train.
- Invalid object shapes, sequence numbers, coordinates and future/naive event timestamps return validation errors instead of poisoning state or crashing ingestion. REST events require identity and occurrence time; misspelled adapters and missing CRIS URLs fail explicitly rather than quietly simulating data.
- Movement state ignores caution/weather records and old demo fixtures. A newer observation cannot be replaced by an older, higher-priority source. Expired inputs hold the last position; metadata distinguishes fallback selection from the source of that held position. Missing WTT data is reported as unavailable, not a fabricated station or time.
- Reported current delay is no longer randomly inflated. Mock ETAs are anchored to the source event, not the time someone refreshes a page. ETA GET requests no longer write forecasts; worker jobs still persist them. Unknown train numbers return 404. Mock prediction/calibration labels replace unsupported calibrated/live claims on the touched displays.
- Structured REST events create train-indexed snapshots, so the existing roster and ETA endpoints can consume them. Route metadata is reused when omitted from a subsequent event, without substituting unrelated scraped geometry.
- The simulator reaches SBC, emits arrivals and departures with stable IDs, identifies each run and repeats its latest boundary reports. Its compressed-time positions are explicitly synthetic; the previously inconsistent speed value is no longer invented. This remains a small demo route, not the complete real timetable.
- Weather polling is separate from train cadence (15 minutes by default). Missing weather timestamps are not replaced with fetch time. Newly retained raw payload hashes now match the actual saved file bytes. Existing historical hashes/files were not rewritten.
- Station departures exclude non-stopping services, retain actual departure reports when a later GPS ping arrives, format actuals in IST, and exclude departures from a previous simulated run.
- Passenger search and refresh responses cannot overwrite a more recently selected train. Controller train details refresh every 30 seconds and ignore late responses after switching/closing. Station switching cancels the old request; R refreshes the selected station, including uppercase R.
- Maps do not render null coordinates as zero or place an unknown train at the route origin. The route is labelled a station-coordinate schematic, not surveyed railway track geometry.
- The station app was missing its Tailwind build pipeline. Restored existing utility styling and corrected overlapping clock/branding/shortcuts and clipped board layout; retained LED styling.
- Docker dependencies wait for database health and completed migrations. Redis and beat have persistent volumes; local ports bind to loopback. The build context excludes `.env`, runtime binaries, archives and collected data.
- Local scripts use the repository directory, prevent duplicate worker/beat launches, and stop auto-seeding stale fixture records during backend startup. `DATABASE_URL` now supplies its actual PostgreSQL connection values; SQLite has a busy timeout.

## Verification

- `venv\Scripts\python.exe manage.py test --verbosity 1`: 28 tests passed.
- `manage.py check`: passed. `manage.py makemigrations --check --dry-run`: no schema changes.
- Passenger, controller and station production builds passed.
- Browser checks: passenger example search returned results; controller selection returned details; station board was visually inspected and keyboard switching/refresh checked.
- Separate worker and beat restarted. `celery -A django_service inspect ping --timeout 5` returned one worker's pong. Beat logs show 30-second scheduling; new simulated RTIS rows and persisted forecasts verified in SQLite.
- Compose YAML/dependency assertions passed. Docker is not installed, so container startup and PostgreSQL/Timescale execution were NOT verified. Unit/eager tests do not substitute for worker integration testing.

## Files changed and why

| File | Purpose |
| --- | --- |
| `django_service/settings.py` | Test isolation, database URL, SQLite timeout, weather cadence |
| `raileta_api/contracts.py` | Input validation |
| `raileta_api/event_store.py` | Shared persistence/deduplication rules |
| `raileta_api/tasks.py` | Shared ingestion and one forecast job per train |
| `raileta_api/views.py` | Validation, truthful empty health, 404, durable ingestion result when broker fails |
| `raileta_api/services.py` | State/freshness correctness, read-only ETA, exact observed delay, station departure fixes |
| `raileta_api/ingestion.py` | Structured adapter validation/roster, simulator destination/run IDs, weather cadence and raw hash |
| `raileta_api/management/commands/collect_public.py` | Failed one-shot collection exits with an error |
| `tests/test_django_api.py` | Explicit fixture for ETA test instead of relying on invented data |
| `tests/test_regressions.py` | 21 additional regression tests |
| `docker-compose.yml`, `.dockerignore` | Readiness, persistence, loopback ports, secret/data exclusions |
| `.env.example` | Document weather interval |
| `START_ALL.ps1`, `start_backend.ps1`, `start_celery_worker.ps1`, `start_celery_beat.ps1`, `start_redis.ps1` | Startup ordering, paths, duplicate protection and safer portable Redis binding |
| `frontend/passenger-ui/src/App.jsx` | Search race protection, refresh error, source/mock labels |
| `frontend/passenger-ui/src/components/RouteNavigator.jsx`, `StationCard.jsx` | Coordinate guards, schematic/mock labels, IST display |
| `frontend/controller-dashboard/src/App.jsx` | Selected-train polling/race handling and source freshness |
| `frontend/controller-dashboard/src/components/CorridorMap.jsx`, `TrainDetailPanel.jsx` | No invented marker/progress; source-route progress and mock labels |
| `frontend/station-display/src/App.jsx` | Request cancellation, R shortcut, non-overlapping layout |
| `frontend/station-display/src/components/Header.jsx`, `DisplayRow.jsx`, `Ticker.jsx` | IST clock, responsive board cells, in-flow footer |
| `frontend/station-display/src/index.css`, `tailwind.config.cjs`, `postcss.config.cjs` | Restore utility CSS compilation |
| `frontend/station-display/package.json`, `pnpm-lock.yaml` | Tailwind/PostCSS/Autoprefixer build dependencies |
| `AUDIT.md` | Findings, verification limits and approval-only proposals |

Generated frontend `dist` bundles were rebuilt. Existing event data was not deleted. Verification logs are in `logs/celery-worker-audit.err` and `logs/celery-beat-audit.err`; the final reloaded worker writes to `logs/celery-worker-final.err`.

## Configuration

- Keep `TESTING=false`, `RAILETA_DATA_ADAPTER=simulated`, `RAILETA_ENABLE_PUBLIC_SCRAPING=false` for this local demo. Runtime eager mode is always false; test runners force isolation.
- Optional `RAILETA_WEATHER_INTERVAL_SECONDS=900`; default already applies without editing `.env`.
- No new API keys, paid services or cloud accounts were obtained. Train events are synthetic. Open-Meteo is weather-model context, not IMD/railway telemetry.
- Future `RAILETA_DATA_ADAPTER=cris_rest` requires an authorized `CRIS_REST_URL` and events matching this application's contract; an arbitrary CRIS endpoint is not automatically compatible. Full routes/schedules and authentication need approved schemas.

## Important unresolved issues

1. **Installed Redis security:** Windows Redis 3.0.504 still listens on `0.0.0.0` and `::`. An attempted protected configuration-file edit failed; this server does not support runtime `CONFIG SET bind`. A configuration rewrite succeeded but did NOT restrict the listener. Its original config was copied to `logs/redis-service-before-audit.conf`. Do not expose this laptop service to an untrusted network. An administrator must bind the service to loopback and restart it, or replace it with the Docker Redis service. No successful hardening is claimed.
2. No official CRIS/RTIS access, verified complete WTT, trained LightGBM, fitted conformal calibration, actual SHAP explanations or demonstrated MAE exists. WTT fallback is a declared fallback state when no baseline is available; it is not yet a real timetable extrapolator.
3. Existing forecast storage overwrites the latest train/station forecast; it is not an immutable backtest history. Timescale hypertables are not implemented just by choosing a Timescale image.
4. Current tests cover serial ingestion and duplicate retries, not distributed-worker contention or production load. Durable dispatch retry/outbox, per-run state locking and dead-letter handling still need design work.
5. The structured adapter supports canonical JSON, not undocumented CRIS schemas/authentication or every feed type promised in the deck (for example charting/ICMS/ESB publishing). Public scraping remains opt-in legacy code; it was not exercised in this audit.

## Proposals - NOT implemented; awaiting your approval

1. **Reliable demo baseline and replay:** a verified MAS-SBC train/station/WTT master plus deterministic replay controls and failure scenarios. Makes the PDF's RTIS -> COA -> WTT fallback demonstrable without confusing simulation with live operation. First requirement: a permitted timetable source and which exact train services/dates to demonstrate.
2. **Evidence-based evaluation:** preserve each forecast with its train run, model version, issue time and eventual actual arrival; report MAE and empirical 80% coverage by lead time. Supports the PDF's shadow rollout. The <5-minute MAE is a target, not a result we can promise before evaluation.
3. **Real forecasting milestone:** build runtime/dwell/loop features, then q10/q50/q90 LightGBM, conformal calibration and controlled top-three SHAP reasons. Keep mock mode until held-out actuals validate it; synthetic data can test software but cannot establish railway accuracy.
4. **Reproducible laptop environment:** install Docker Desktop/WSL2 and run supported Linux workers, PostgreSQL and Redis there, then test one-command startup, restart recovery and disconnected demonstrations. This replaces the old Windows Redis/Celery workaround without adding cloud dependence.

References checked: [Docker startup readiness](https://docs.docker.com/compose/how-tos/startup-order/), [Celery testing limitations](https://docs.celeryq.dev/en/main/userguide/testing.html), [Celery Windows support](https://docs.celeryq.dev/en/main/faq.html), [Redis installation guidance](https://redis.io/docs/latest/operate/oss_and_stack/install/install-stack/). The environment proposal follows those runtime constraints; the product proposals above follow the submitted PDF rather than extending the product into dispatch control or GPS navigation.
