"""Minimal .env loader. Placeholder values (REPLACE_ME) and already-set
variables are never written into the environment, so a half-filled .env
cannot make an engine look configured."""

import os
from pathlib import Path

PLACEHOLDER = "REPLACE_ME"


def load_env_file(path: "str | Path") -> None:
    p = Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if not key or not value or value == PLACEHOLDER or key in os.environ:
            continue
        os.environ[key] = value
