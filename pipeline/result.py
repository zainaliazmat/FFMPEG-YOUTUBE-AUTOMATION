"""The result envelope.

Every stage script returns a JSON object ``{"success": bool, "error": str|None, ...}``
and never raises to its caller. ``run`` also persists the envelope to a known file,
``project/<slug>/.result.json``, so the orchestrator can read it reliably even though
kokoro / whisperx / ffmpeg print freely to stdout (fix #6 — never rely on "the last
stdout line").
"""
import json
from pathlib import Path


def ok(**fields):
    return {"success": True, "error": None, **fields}


def err(message, **fields):
    return {"success": False, "error": str(message), **fields}


def _result_path(slug, root="project"):
    return Path(root) / slug / ".result.json"


def run(fn, slug=None, root="project"):
    try:
        r = fn()
    except Exception as exc:  # noqa: BLE001 - scripts must never raise to caller
        r = err(str(exc))
    print(json.dumps(r))
    if slug is not None:
        path = _result_path(slug, root)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(r, indent=2))
    return r
