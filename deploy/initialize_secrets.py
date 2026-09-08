"""Run ON THE SERVER once; never prints or overwrites existing credentials."""
import os
from pathlib import Path
import secrets
import subprocess

root = Path(__file__).resolve().parent.parent
env_file = root / '.env.azure'
access_file = root / 'team-access.txt'
if env_file.exists() or access_file.exists():
    raise SystemExit('Existing credentials found; refusing to overwrite.')
password = secrets.token_urlsafe(24)
hashed = subprocess.run(
    ['sudo', '-n', 'docker', 'run', '--rm', '-i', 'caddy:2-alpine',
     'caddy', 'hash-password'], input=password + '\n', text=True,
    capture_output=True, check=True,
).stdout.strip()
if not hashed.startswith('$2'):
    raise SystemExit('Unexpected password hash; no credentials written.')
config = '\n'.join([
    'SITE_ADDRESS=localhost',
    'TEAM_USERNAME=raileta-team',
    # Literal single quotes stop Compose from interpolating bcrypt dollar signs.
    f"TEAM_PASSWORD_HASH='{hashed}'",
    f'DJANGO_SECRET_KEY={secrets.token_urlsafe(48)}',
    f'POSTGRES_PASSWORD={secrets.token_urlsafe(36)}',
    '',
])
for destination, content in [
    (env_file, config),
    (access_file, f'RailETA Azure team access\nUsername: raileta-team\nPassword: {password}\nKeep private. Do not commit.\n'),
]:
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as output:
        output.write(content)
print('Created server-only secrets and team access file (mode 0600).')
