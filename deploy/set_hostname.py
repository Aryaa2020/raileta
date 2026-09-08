"""Set the public hostname without displaying or replacing credentials."""
from pathlib import Path
import re
import sys

hostname = sys.argv[1]
if not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", hostname):
    raise SystemExit("Expected a DNS hostname, without a URL or path.")
path = Path(__file__).resolve().parent.parent / ".env.azure"
content = path.read_text()
updated, count = re.subn(r"^SITE_ADDRESS=.*$", f"SITE_ADDRESS={hostname}", content, flags=re.M)
if count != 1:
    raise SystemExit("Expected exactly one SITE_ADDRESS setting.")
path.write_text(updated)
path.chmod(0o600)
print(f"Configured hostname: {hostname}")
