# RailETA change log

Record user-visible changes, limitations, and checks with each completed change.
Git commits preserve exact file history; milestone tags identify saved releases.

## Unreleased

## 0.2.2-demo — 2026-09-09

- Bundled Ubuntu fonts across the shared theme. Opening a train scrolls to the
  unified arrival/route panel beneath navigation; reduced motion is respected,
  and automatic refreshes preserve the reader's scroll position.

- Passenger search now accepts train names, partial numbers, station names/codes,
  city aliases such as Bangalore/BLR, and directed routes such as MAS to SBC.
  Search is limited to the available demo roster and its actual stopping patterns.
- Passenger reports lead with the selected stop's arrival time, an arrival window
  and a plain-language schedule comparison. Added a purple vertical stop timeline,
  last-reported train marker and progress. Actual, missing and stale estimates stay
  distinct; IST calendar dates make overnight arrivals clear. Detailed tables and
  forecast history remain available below the passenger summary.
- Fixed the public deployment smoke test's obsolete credential read and its
  mobile navigation lookup; updated it for the new passenger report.

## 0.2.1-demo — 2026-09-09

- Removed the shared username/password gate from the public Azure demo. The
  passenger, controller, station and same-origin API routes are now reachable
  without a login prompt; private server secrets remain off-repository.
- Updated the Caddy deployment, clean-server secret initializer and public smoke
  test so future releases preserve the public-access behavior.

## 0.2.0-demo — 2026-09-09

- Rebuilt all three dashboards with a shared black/purple theme, simplified
  journey reports, accessible stop progress and responsive navigation. Passenger
  typography and full-width railway track reveal respect reduced motion;
  the operations dashboard stays functional and animation-free.
- Added dated journeys, ordered overnight timetables, forecast history, station
  arrivals, read-only section conditions, destination outlook and accuracy views.
- Replaced the active aggregate-profile demo with explicitly labelled Chennai–
  Bengaluru simulation: real service numbers/stopping patterns, generated events.
  Five-year corpus: 7,043 journeys, 331,061 training/evaluation samples and
  4,764,228 feed records. Large generated corpora remain local and reproducible;
  the generator, reference snapshot and trained model bundle are versioned.
- LightGBM q10/q50/q90, conformal calibration, TreeSHAP and stale-data safeguards
  retained. Synthetic held-out MAE 4.69 min, measured coverage 80.14%; harder
  synthetic stress coverage 72.23%. These are not real-world accuracy claims.
- Added immutable model registration for clean-server deployment, hash checks,
  simulation-only activation, shared-component Docker builds and same-origin
  dashboard links. Existing server credentials and database history are retained.
- Release checks: all 60 Django tests and all three production UI builds passed,
  including model registration, corruption rejection and live/simulation isolation.
  Staged source passed credential-pattern/local-secret checks, and model bytes
  match the immutable artifacts. Azure rollout is a separate
  operation; this entry does not assert that the VM has already been updated.

### Earlier deployment work included in this release

- Added a server-side login rotation helper accepting credentials through stdin.
  Rotated the shared dashboard login; verified all dashboards/API accept the new
  login and reject the previous one. Credentials are not stored in source control.
- Added single-VM Azure deployment for passenger, controller and station UIs,
  same-origin API, Caddy HTTPS and shared team authentication. Database and Redis
  ports remain private; persistent volumes and separate worker/beat services are
  configured. Credentials are generated server-side and excluded from Git/builds.
- Added deployment instructions, hostname configuration and authenticated public
  browser smoke test. No model, data claims or dashboard styling changed.
- Azure verification (2026-09-08): 37 Django tests passed; all three public HTTPS
  dashboards, authenticated ETA API, desktop/mobile scroll transitions passed.
  Unauthenticated requests return 401; Redis and Celery ping respond, and replay
  jobs persist a new historical profile every 15 seconds. Valid TLS certificate
  obtained for raileta.indiasouthcentral.cloudapp.azure.com.

## 0.1.0-demo — 2026-09-07

Initial project checkpoint, based on the existing GitHub README history.

- Django/DRF backend, event adapters, Celery/Redis process configuration, and
  three React dashboards retained.
- Active demo uses held-out etrain aggregate-delay profiles and frozen LightGBM
  quantiles with SHAP; it is not live train tracking or per-run ETA validation.
  TEST MAE 24.52 minutes and coverage 70.29%; see the experiment report for scope.
- Passenger landing fits the viewport, keeps search accessible, supports reverse
  scrolling before selection, and locks out the cover after selection.
- Cover train icon stays horizontally centered instead of sliding or rotating.
- Hardened upload exclusions for credentials, local data, caches, and process
  state. Replaced the source's local-secret fallback with a generated fallback;
  configured deployments should supply a persistent shared environment key.
- Added team setup, review/checkpoint workflow, and backup-scope documentation.
- Preserved dataset/model bytes across Git checkouts so Windows line-ending
  conversion cannot invalidate the frozen model's integrity checks.

Checkpoint verification: 37 Django tests and 37 historical UI render assertions
passed. The latest cover-logo change also passed its desktop/mobile browser
regression and passenger production build. Candidate files were checked for
recognisable token/private-key patterns and matches to local environment secrets;
neither check found remaining matches. These checks are not a comprehensive
security audit.

This checkpoint does not imply earlier development was already versioned, that
the model met its accuracy targets, or that Docker was runtime-verified.
