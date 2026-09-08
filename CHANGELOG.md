# RailETA change log

Record user-visible changes, limitations, and checks with each completed change.
Git commits preserve exact file history; milestone tags identify saved releases.

## Unreleased

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
