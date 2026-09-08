# Azure single-VM deployment

This configuration serves the existing passenger dashboard at `/`, controller at
`/controller/`, and station board at `/station/`. All use the same-origin API.
Caddy protects all three dashboards and the API with a shared team login and
obtains HTTPS certificates when public DNS and inbound TCP 80/443 are available.
PostgreSQL, Redis and the backend have no host-published ports.

## Initial setup

On an Ubuntu VM with Docker and Docker Compose installed, put a clean source
archive in `/home/azureuser/raileta`. Do not copy laptop environment files or keys.
Run from that directory:

```sh
python3 deploy/initialize_secrets.py
python3 deploy/set_hostname.py YOUR_FULL_DNS_NAME
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml build api web
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml up -d --no-build
```

The initializer refuses to overwrite existing credentials. `.env.azure` and
`team-access.txt` are private, ignored files. Share the team login privately;
never publish these files or the SSH private key. Shared authentication does not
provide individual user accounts or per-person audit trails.

## Operations

```sh
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml ps
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml logs --tail=50 worker beat
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml exec -T redis redis-cli ping
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml exec -T worker celery -A django_service inspect ping
sudo docker compose --env-file .env.azure -f deploy/compose.azure.yml exec -T api python manage.py replay_profiles
```

Docker starts on boot; service restart policies recover containers. Named volumes
persist database, Redis, replay scheduling and TLS state. Do not run `down -v`:
that deletes deployment data. Persistent volumes are not off-machine backups.
Back up PostgreSQL with `pg_dump` and store an encrypted copy separately before
major upgrades. Retain the server secrets securely for recovery.

The demo replays held-out aggregate historical profiles every 15 seconds and
stops at the end of the dataset. It is not live tracking or individual dated
train runs. Replay completion is expected, not a collector failure. Do not reset
automatically or present it as fresh observations. The frozen model is unchanged;
its measured TEST MAE is 24.52 minutes and coverage is 70.29%, not the 80% target.

## Updates

Commit and test source changes locally first. Transfer a clean `git archive` of
the chosen commit into a new release directory on the VM. Transfer the existing
server-only `.env.azure` securely into that directory (mode 0600), then build and
run the commands above. Compose project name `raileta` keeps the same volumes.
Keep the previous source and image IDs for rollback; database migrations may
require restoring a compatible backup, not just an old image. Dependencies have
version ranges, so rebuilding later can select different package versions.

This is one laptop-sized VM, not a highly available production service. Azure
credits, VM uptime, security updates, backups and domain/IP configuration still
need maintenance. Stop/deallocate the VM when not needed to reduce compute use;
the dashboards are unavailable while it is stopped, and other charges may remain.
