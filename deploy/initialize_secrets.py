"""Run ON THE SERVER once; never prints or overwrites existing credentials."""
import os
from pathlib import Path
import secrets

root = Path(__file__).resolve().parent.parent
env_file = root / '.env.azure'
if env_file.exists():
    raise SystemExit('Existing credentials found; refusing to overwrite.')
config = '\n'.join([
    'SITE_ADDRESS=localhost',
    f'DJANGO_SECRET_KEY={secrets.token_urlsafe(48)}',
    f'POSTGRES_PASSWORD={secrets.token_urlsafe(36)}',
    '',
])
descriptor = os.open(env_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(descriptor, 'w') as output:
    output.write(config)
print('Created server-only Django and database secrets (mode 0600).')
