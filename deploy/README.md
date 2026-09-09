# Azure single-VM deployment

This configuration serves the existing passenger dashboard at `/`, controller at
`/controller/`, and station board at `/station/`. All use the same-origin API.
Caddy serves all three dashboards and the API publicly, and obtains HTTPS
certificates when public DNS and inbound TCP 80/443 are available.
PostgreSQL, Redis and the backend have no host-published ports.

## Initial setup

On an Ubuntu VM with Docker and Docker Compose installed, put a clean source
archive in `/home/azureuser/raileta`. Do not copy laptop environment files or keys.
Run from that directory:

```sh
python3 deploy/initialize_secrets.py
python3 deploy/set_hostname.py YOUR_FULL_DNS_NAME
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml build api web
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml up -d db redis
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml run --rm --no-deps migrate
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml run --rm --no-deps api python manage.py journey_model register --model-version mas-sbc-synthetic-v1 --mode simulation
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml run --rm --no-deps api python manage.py journey_model activate --model-version mas-sbc-synthetic-v1
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml run --rm --no-deps api python manage.py replay_corridor --history-days 7
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml up -d --no-build
```

The initializer refuses to overwrite existing server secrets. `.env.azure` is a
private, ignored file; never publish it or the SSH private key. Public access is
intentional for this demo, so add an identity-aware access layer before using
operational or private data.

## Operations

```sh
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml ps
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml logs --tail=50 worker beat
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml exec -T redis redis-cli ping
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml exec -T worker celery -A django_service inspect ping
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml exec -T api python manage.py check
```

Docker starts on boot; service restart policies recover containers. Named volumes
persist database, Redis, replay scheduling and TLS state. Do not run `down -v`:
that deletes deployment data. Persistent volumes are not off-machine backups.
Back up PostgreSQL with `pg_dump` and store an encrypted copy separately before
major upgrades. Retain the server secrets securely for recovery.

The demo advances explicitly synthetic dated Chennai–Bengaluru journeys through
Celery's isolated `raileta-synthetic` queue every 15 seconds. The clock runs at
10x by default and stops after 24 simulated hours; it never rewinds issued history.
Run `replay_corridor` only for initial setup: an existing session is preserved and
the command refuses to replace it. This is not live tracking. The bundled model
was trained on five years of generated data; held-out synthetic MAE is 4.69 min,
coverage 80.14%, and harder stress coverage 72.23%, not a real-world guarantee.
Only the compact model/reference files are baked into the image; the multi-million
record corpus can be reproduced offline using [the simulation guide](../docs/corridor-simulation.md).

## Updates

Commit and test source changes locally first. Transfer a clean `git archive` of
the chosen commit into a new release directory on the VM. Transfer the existing
server-only `.env.azure` securely into that directory (mode 0600), then build and
run the commands above. Compose project name `raileta` keeps the same volumes.
Stop the old worker and beat before migrations, take a consistent `pg_dump`, and
save the old backend/web image IDs under rollback tags before building replacements.
Never copy laptop secrets or a laptop database. Registration is idempotent and
validates bundle checksums without overwriting a version; activation is separate.
Skip initial replay when a `mas-sbc` simulation session already exists.
Keep the previous source and image IDs for rollback; database migrations may
require restoring a compatible backup, not just an old image. Dependencies have
version ranges, so rebuilding later can select different package versions.

This is one laptop-sized VM, not a highly available production service. Azure
credits, VM uptime, security updates, backups and domain/IP configuration still
need maintenance. Stop/deallocate the VM when not needed to reduce compute use;
the dashboards are unavailable while it is stopped, and other charges may remain.
