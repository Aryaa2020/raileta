"""Run on the server with username/password JSON on stdin; never logs secrets."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys

credentials = json.load(sys.stdin)
username, password = credentials['username'], credentials['password']
if not re.fullmatch(r'[A-Za-z0-9_-]+', username) or not password or '\n' in password or '\r' in password:
    raise SystemExit('Invalid login format.')
root = Path(__file__).resolve().parent.parent
env_file = root / '.env.azure'
content = env_file.read_text()
hashed = subprocess.run(
    ['sudo', '-n', 'docker', 'run', '--rm', '-i', 'caddy:2-alpine',
     'caddy', 'hash-password'], input=password + '\n', text=True,
    capture_output=True, check=True,
).stdout.strip()
if not hashed.startswith('$2'):
    raise SystemExit('Unexpected password hash.')
for name, value in [('TEAM_USERNAME', username), ('TEAM_PASSWORD_HASH', f"'{hashed}'")]:
    content, count = re.subn(rf'^{name}=.*$', lambda _: f'{name}={value}', content, flags=re.M)
    if count != 1:
        raise SystemExit(f'Expected exactly one {name} setting.')
for path, value in [
    (env_file, content),
    (root / 'team-access.txt', f'RailETA Azure team access\nUsername: {username}\nPassword: {password}\nKeep private. Do not commit.\n'),
]:
    temporary = path.with_name(path.name + '.rotation')
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(value)
    os.replace(temporary, path)
print('Updated login files; recreate the web service to activate.')
