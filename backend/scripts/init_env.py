"""Create backend/.env from .env.example with freshly generated local secrets.

Usage:  python scripts/init_env.py [--database-url URL] [--force]
Existing non-empty values in .env are kept unless --force is given.
"""

from __future__ import annotations

import argparse
import base64
import secrets
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
EXAMPLE = BACKEND / ".env.example"
TARGET = BACKEND / ".env"


def parse(path: Path) -> dict[str, str]:
    values = {}
    if path.exists():
        for line in path.read_text().splitlines():
            if line and not line.lstrip().startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                values[key.strip()] = value.strip()
    return values


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--database-url")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    existing = {} if args.force else parse(TARGET)
    generated = {
        "SECRET_KEY": secrets.token_hex(32),
        "VOTE_ENCRYPTION_KEY": base64.b64encode(secrets.token_bytes(32)).decode(),
        "IDENTIFIER_PEPPER": secrets.token_hex(32),
    }
    if args.database_url:
        generated["DATABASE_URL"] = args.database_url

    out = []
    for line in EXAMPLE.read_text().splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key = line.partition("=")[0].strip()
            if existing.get(key):
                value = existing[key]
            elif key in generated:
                value = generated[key]
            else:
                value = line.partition("=")[2]
            out.append(f"{key}={value}")
        else:
            out.append(line)
    TARGET.write_text("\n".join(out) + "\n")
    TARGET.chmod(0o600)
    print(f"Wrote {TARGET} (permissions 600). Keep it out of version control.")


if __name__ == "__main__":
    main()
