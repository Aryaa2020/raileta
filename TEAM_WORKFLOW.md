# RailETA team setup and version history

Repository: https://github.com/Aryaa2020/raileta (private).

## Access

The owner invites each teammate through repository Settings > Collaborators.
Accept the invitation using your own GitHub account. Do not share passwords,
personal access tokens, or the owner's GitHub login.

## Get the project

Install Git, Python, and Node.js on your computer. Sign in when Git prompts you.
The existing laptop has Python 3.14; dependencies must support your chosen Python
version. This repository does not include installed dependencies.

```powershell
git clone https://github.com/Aryaa2020/raileta.git
cd raileta
python -m venv venv
.\venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
.\venv\Scripts\python.exe -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Put the generated key in your local `.env` as `DJANGO_SECRET_KEY`. Do not paste
it into an issue, documentation, chat, or commit. Keep the offline
`RAILETA_DATA_ADAPTER=historical_profiles` defaults. Each teammate uses their own
local database. The tracked CSV and frozen model files reproduce the profile
demo; the original laptop's database is not required.

Follow **Run locally** in [HISTORICAL_PROFILE_RESULTS.md](HISTORICAL_PROFILE_RESULTS.md)
for migrations, replay, worker/beat, and model details. Follow the frontend
README files to install dependencies and run the three dashboards. Docker Compose
is included, but has not been runtime-verified on the original laptop. Configure
one persistent `DJANGO_SECRET_KEY` for all Django/Celery services.

## Save each completed change

A commit is a local version checkpoint. A push copies commits to GitHub. Neither
happens merely because a file was saved; no timer or automatic upload is enabled.

Start from an up-to-date `main` with a clean working tree:

```powershell
git switch main
git pull --ff-only
git switch -c fix/describe-your-change
```

Make the change, test it, and add a short entry under **Unreleased** in
[CHANGELOG.md](CHANGELOG.md). Review exactly what will be uploaded:

```powershell
git status --short
git diff
# Replace these example paths with the files you intentionally changed:
git add -- frontend/passenger-ui/src/App.jsx CHANGELOG.md
git diff --cached
git commit -m "fix: describe what changed and why"
git push -u origin HEAD
```

Open a pull request on GitHub and have a teammate review it before merging.
Do not force-push, overwrite another teammate's work, or resolve conflicts by
discarding changes you do not understand. If `pull --ff-only` fails, stop and
resolve the differing histories together. Configure your own Git author name
and GitHub-provided private email before your first commit.

For a milestone, after merging and updating `main`, the owner can create an
annotated tag such as `v0.2.0-demo` and push that exact tag. Tags identify stable
versions; they do not create extra copies of the project folder.

```powershell
git log --oneline --decorate -15
git tag --list
# Explore an older milestone safely in a separate working directory:
git worktree add --detach ../raileta-old-demo v0.1.0-demo
```

The initial GitHub README commit is preserved. Work done before the first project
checkpoint is not magically recoverable as individual Git commits. Older model
directories retained in this checkpoint are inactive historical artifacts, not
current model claims.

## Checks before a checkpoint

```powershell
.\venv\Scripts\python.exe manage.py test tests
node frontend/tests/historical-replay-smoke.mjs
```

Build each changed frontend with `npm run build` from its folder. Browser tests
under `frontend/tests/` require Playwright and Microsoft Edge; most also need the
local dashboards/backend running. `RAILETA_PLAYWRIGHT_PATH` can select a custom
Playwright installation. Do not claim tests ran unless you actually ran them.

## What this backup includes and excludes

Included: backend/frontend source, migrations, tests, startup/container config,
safe `.env.example` templates, documentation, the supplied etrain CSV, and frozen
model/split/evaluation artifacts. Dataset provenance and redistribution terms
remain unverified: keep the repository private and verify permissions before
redistributing or publishing the data.

Excluded: real `.env` files and credentials, databases and their WAL/SHM files,
Redis/Celery state, raw captures/exports, logs/screenshots, old local archives,
installed dependencies, build outputs, and bundled runtime executables.

This is a source-and-model backup, not a full disk/database backup. If you need
the exact local prediction/ingestion history, make a separate consistent SQLite
backup (using SQLite's backup API) or PostgreSQL dump to secure backup storage.
Do not copy a running SQLite file alone or commit credentials/database dumps.
No database backup or background autosync is configured by these instructions.
