# Chennai–Bengaluru synthetic model replacement

## What is active

The local demo now selects `RAILETA_DATA_ADAPTER=corridor_simulation` and the
simulation-only release `mas-sbc-synthetic-v1`. It no longer trains on or serves
`etrain_delays.csv` aggregate profiles. Old datasets/models remain untouched for
rollback; nothing was silently destroyed. Live-mode records and releases are separate.

The passenger and controller train selections open dated journeys, actual-versus-
forecast timelines, forecast history, calibrated windows and signed SHAP factors.
The station board explicitly labels simulation and leaves platforms unavailable.
An accelerated scenario clock is shown; these are NOT today's services. Page reads
never generate events, outcomes, or predictions. Celery/Redis advances the replay.

## PDF review and boundaries

Read all six pages of `C:/Users/aryaa/Downloads/final final.pdf`, including the
architecture diagram. Pages 2–4 require downstream, event-driven arrival forecasts,
RTIS/REMMLOT/COA/context adapters, LightGBM q10/q50/q90, non-crossing intervals,
conformal calibration, SHAP, stale safeguards, auditable predictions and controlled
retraining. The PDF's 80% coverage and <10 ms latency are targets, not certification.
Its quoted 32% prototype improvement is not reused as a result of this experiment.

The PDF is a proposal, not an official CRIS schema, source access grant, timetable,
delay distribution, or validated working timetable. We cannot reconstruct actual
railway history or every official field from it. The synthetic corpus tests the
software and forecasting workflow, not operational safety or real-world accuracy.

## Real reference versus generated assumptions

Frozen public timetable snapshot: `data/reference/chennai_bengaluru.json`, checked
2026-09-09. Train identities, scheduled calling stops, times and cumulative distances
come from published timetable pages. Average-delay columns are **not used**.

- [12027 Chennai–Bengaluru Shatabdi](https://www.confirmtkt.com/train-schedule/12027): six days, excluding Tuesday; MAS, KPD, JTJ, BNC, SBC.
- [12607 Lalbagh](https://www.confirmtkt.com/train-schedule/12607): daily; 13 calling stations.
- [12639 Brindavan](https://www.confirmtkt.com/train-schedule/12639): daily; 13 calling stations.
- [12657 Chennai–Bengaluru Mail](https://www.confirmtkt.com/train-schedule/12657): daily; 8 calling stations and next-day arrivals.
- [Indian Railways Shatabdi list](https://indianrail.gov.in/shatabdi_trn_list.html) corroborates 12027's identity; its older timing is not substituted for the frozen snapshot.

This is one direction, MAS–SBC, not every service traversing the corridor. The
snapshot is repeated across synthetic years, not presented as each year's actual
timetable. Public passenger schedules are not official WTT recovery allowances.

| Input family | Generated representation and limitations |
|---|---|
| RTIS/REMMLOT-like movement | Nominal 30-second pings, chainage, speed, delayed receipts and dropped reports. Coordinates interpolate approximate station anchors: schematic, not surveyed railway geometry. |
| COA | Per-run arrival/departure events, unique IDs, source/receipt times, ordered stops and explicit overnight dates. Late reports cannot move state backwards. |
| WTT/section context | Published passenger schedule plus assumed double track, speed cap and recovery allowance. These infrastructure values are not verified railway data. |
| Caution/network context | Shared daily restriction/block/congestion scenarios, background traffic and precedence exposure; correlated across services. Not a signalling or dispatch microsimulation. |
| Weather | Shared seasonal rain and visibility priors, not actual IMD observations or per-section sensors. |
| ICMS-like context | Explicitly assumed consist/traction metadata retained in raw records; not an authenticated ICMS schema and not all fields are model inputs. |

All generated records carry `mode=simulation` and `SYNTHETIC_MAS_SBC_V1`. No platform
assignments are generated. The 28-feature model uses COA issuance snapshots, recent
section speed/delay trend, remaining schedule/distance/stops, assumed recovery/
infrastructure/priority, weather, network conditions and input ages. Raw GPS is
retained for adapter development; this release does **not** independently reforecast
on each GPS ping. Its running demo advances on COA events, using the dated pipeline.

Runtime physics enforce positive section times, no departure before schedule,
chronological actual arrivals and a 130 km/h scenario cap. Outcomes include bounded
recovery, dwell variation, shared weather/congestion and unobserved heavy-tail
disruptions. Observations and future innovations use separate deterministic random
streams. The generator is not fitted to measured delay distributions; increasing
the number of generated years does not eliminate simulator bias.

## Corpus and measured results

Generated 2021-01-01 through 2025-12-31 with seed 26028:

- 7,043 dated journeys; 331,061 downstream forecast examples.
- 4,764,228 feed records, including 4,610,324 position pings.
- Immutable gzip JSONL files and checksummed manifest under
  `data/processed/mas-sbc-synthetic-v1/` (about 240 MB compressed).
- Raw feed is grouped by journey/type; consume by `received_at`, not file order.
- Stale COA reports are retained in raw events but do not become fresh training issues.

Train: 198,419 examples, 2021-01-01–2023-12-31. Calibration: 66,254 examples,
2024-01-01–2024-12-30. Test: 66,388 examples, 2024-12-31–2025-12-31.
Every issued snapshot and target from a dated run stays in one split. No aggregate
records or future outcomes enter the predictors. Test data is not used to pick
hyperparameters or adjust calibration. Quantile bounds are monotonically ordered,
with finite-sample split-conformal correction; month-specific corrections use only
calibration examples and fall back to the global correction when insufficient.

| Synthetic evaluation | Mean absolute error | Current-delay baseline | Measured coverage |
|---|---:|---:|---:|
| Held-out dates | 4.69 min | 6.00 min | 80.14% |
| Harder scenario, 16,343 examples | 7.86 min | 8.70 min | 72.23% |

Mean held-out window width: 12.63 minutes. Coverage varies: 77.36% at leads over
two hours and 74.91% in June. **80% is not assured for every season or lead time.**
The harder scenario uses seed 91377, more hidden disruptions/blocks and stronger
rain; it is reported independently, not used for fitting or calibration. Neither
evaluation is independent validation of the generator against railway operations.

All details are in `data/models/journeys/mas-sbc-synthetic-v1/manifest.json`.
Activation uses existing held-out sample/error/coverage gates and is restricted
to simulation. The stress failure remains visible in the controller. Model text
files and manifests are checksummed, never unpickled. Top-three signed TreeSHAP
attributions use controlled labels and run in the forecast worker, not browser GETs.

## Reproduce and run

```powershell
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py build_corridor_corpus generate --directory data/processed/mas-sbc-synthetic-v1
.\venv\Scripts\python.exe manage.py build_corridor_corpus train --directory data/processed/mas-sbc-synthetic-v1 --model-version mas-sbc-synthetic-v1
.\venv\Scripts\python.exe manage.py journey_model activate --model-version mas-sbc-synthetic-v1
.\venv\Scripts\python.exe manage.py replay_corridor --at 2026-01-15T18:30:00+05:30 --speed 10 --history-days 7
```

Use new corpus/model version names for another build; commands reject overwrites.
The replay command creates one session and rejects accidental rewind. It loads
seven days of post-training synthetic history into the interactive database, plus
the current scenario. All five generated years remain in the corpus files, not
millions of UI rows. The clock is bounded to 24 simulated hours and does not loop
or relabel old runs as new data. Restarting the collector resumes its clock.

With Redis running, the existing worker and beat scripts start processing.
`corridor_simulation` uses the isolated `raileta-synthetic` queue. The API must be
restarted after changing `.env`. A manual one-shot check is
`manage.py collect_events --once`; the production-shaped path is Celery beat/worker.
Stale station reports hold previous forecasts and remain explicitly flagged;
the application does not manufacture a fresh position or validated wider window.

Automatic live retraining remains opt-in and cannot train on this simulation
namespace. Official feed authentication, CRIS schema mapping, real WTT/section data,
RTIS-driven runtime state and real dated labels are still required before any live
deployment. No publication to CRIS/NTES/IPIS or real platform operations occurred.

Rollback: set `RAILETA_DATA_ADAPTER=historical_profiles` and restore the old roster
if using the legacy event adapter, then restart API/worker/beat. Original data and
models are intact. Historical and synthetic schemas remain deliberately incompatible.

## Verification

```powershell
.\venv\Scripts\python.exe manage.py test tests.test_corridor_simulation tests.test_journeys tests.test_django_api tests.test_regressions tests.test_profile_replay
node frontend/tests/corridor-simulation-browser.cjs
```

Tests cover train-specific stops, overnight dates, physically possible movement,
determinism, no future-label leakage, stale receipts, train/inference feature parity,
idempotent dated events, read-only GETs, mode isolation, bounded scenario time and
existing forecasting/calibration safeguards. Browser verification covers both
desktop and mobile, model provenance and simulation labels. Three Vite builds are
checked separately. These are software checks, not operational validation.
