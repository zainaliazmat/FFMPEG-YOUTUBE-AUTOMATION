"""Per-video project folder + manifest.json helpers.

The manifest is the single source of truth across stages. Phase-1 stages are
voice -> media -> captions -> stitch. (Music is an optional local file, not a
fetched stage; guard/publish are Phase 2.)
"""
import json
from datetime import datetime, timezone
from pathlib import Path

STAGES = ("capture", "voice", "media", "captions", "stitch")


def project_dir(slug, root="project"):
    d = Path(root) / slug
    for sub in ("", "audio", "media", "out"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _manifest_path(slug, root="project"):
    return project_dir(slug, root) / "manifest.json"


def init(slug, root="project"):
    # Idempotent: seed any missing base stages but NEVER clobber existing stage
    # data. yt-script runs init on every (re)run; a blind overwrite here would
    # wipe stages.capture / stages.media when the script is regenerated, silently
    # orphaning already-captured PNGs and fetched b-roll (autoplan eng F4).
    try:
        data = load(slug, root)
    except FileNotFoundError:
        data = {
            "slug": slug,
            "created": datetime.now(timezone.utc).isoformat(),
            "stages": {},
        }
    data.setdefault("slug", slug)
    data.setdefault("stages", {})
    for s in STAGES:
        data["stages"].setdefault(s, {"status": "pending"})
    save(slug, data, root)
    return data


def load(slug, root="project"):
    return json.loads(_manifest_path(slug, root).read_text())


def save(slug, data, root="project"):
    _manifest_path(slug, root).write_text(json.dumps(data, indent=2))


def set_stage(slug, stage, root="project", **fields):
    try:
        data = load(slug, root)
    except FileNotFoundError:
        # A stage may run before any orchestrator initialized the manifest.
        data = init(slug, root)
    data["stages"].setdefault(stage, {}).update(fields)
    save(slug, data, root)
    return data


def stage_done(slug, stage, root="project"):
    try:
        return load(slug, root)["stages"].get(stage, {}).get("status") == "done"
    except FileNotFoundError:
        return False
