"""Minimal .env loader — no third-party dependency.

Reads KEY=VALUE lines from a .env file into os.environ WITHOUT overwriting
variables that are already set (a real exported env always wins). Keeps secrets
(API keys) out of source while staying dependency-free.
"""
import os
from pathlib import Path


def load_dotenv(path=".env"):
    p = Path(path)
    if not p.is_file():
        return
    for raw in p.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value
