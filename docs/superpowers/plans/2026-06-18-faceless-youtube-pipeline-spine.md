# Faceless YouTube Pipeline — Spine v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn one hand-authored `script.json` into a captioned video in both 9:16 and 16:9, on a CPU-only Linux box, using only free/local tooling.

**Architecture:** A shared `pipeline/` Python package provides the result envelope, project-folder + manifest helpers, and `script.json` validation. Four single-responsibility skills (`yt-voice`, `yt-media`, `yt-captions`, `yt-stitch`) each wrap one Python script that reads/writes a per-video project folder and returns a `{"success": bool, "error": ...}` JSON envelope. A `yt-make` orchestrator runs them in order behind a human approval gate on the script. Heavy/IO-bound work (Kokoro, WhisperX, FFmpeg, HTTP) sits in thin wrappers around pure, unit-tested core functions (command building, caption segmentation, API-response parsing, timeline math).

**Tech Stack:** Python 3.12, Kokoro-82M (`kokoro`, `soundfile`, `espeak-ng`), WhisperX (`whisperx`), `pysbd`, `requests`, system `ffmpeg`/`ffprobe`, `pytest`.

## Global Constraints

- Python 3.12; all deps pinned in `requirements.txt`; work inside a project venv `.venv`.
- 100% free/local only. TTS = **Kokoro-82M (Apache-2.0)** — never F5-TTS or XTTS-v2.
- Media only from **Pexels** (primary) and **Pixabay** (fallback + music); music = Pixabay CC0 or YouTube Audio Library only.
- Media rules: download to local disk (no hotlinking); 24h response cache; exponential backoff on HTTP 429; every asset's source+license logged into `manifest.json`.
- CPU-only: assembly is **pure FFmpeg** (no MoviePy); Kokoro and WhisperX run in CPU mode.
- Every script's stdout is a single JSON object `{"success": bool, "error": str|null, ...}`; scripts never raise to the caller — they catch and return the envelope.
- Stages are idempotent: a stage whose manifest `status == "done"` is skipped unless `--force`.
- Output video: `yuv420p`, `+faststart`; 9:16 = 1080×1920, 16:9 = 1920×1080.
- TDD: failing test first, minimal impl, commit per task. API keys read from env: `PEXELS_API_KEY`, `PIXABAY_API_KEY`.

---

### Task 1: Shared `pipeline` package — result envelope, manifest, schema

**Files:**
- Create: `pipeline/__init__.py`
- Create: `pipeline/result.py`
- Create: `pipeline/manifest.py`
- Create: `pipeline/schema.py`
- Create: `requirements.txt`
- Create: `.gitignore`
- Test: `tests/test_result.py`, `tests/test_manifest.py`, `tests/test_schema.py`
- Create: `fixtures/script.json`

**Interfaces:**
- Produces:
  - `result.ok(**fields) -> dict` → `{"success": True, "error": None, **fields}`
  - `result.err(message: str, **fields) -> dict` → `{"success": False, "error": message, **fields}`
  - `result.run(fn) -> dict` — calls `fn()`, returns its dict, or `err(str(exc))` on exception; prints `json.dumps(result)` to stdout and returns it.
  - `manifest.project_dir(slug: str, root="project") -> Path` (creates `project/<slug>/` and `audio/`, `media/`, `out/` subdirs)
  - `manifest.load(slug) -> dict`, `manifest.save(slug, data) -> None`
  - `manifest.init(slug) -> dict` (creates a manifest with all stages `status="pending"`)
  - `manifest.set_stage(slug, stage, **fields) -> dict` (merges fields into `stages[stage]`, persists, returns manifest)
  - `manifest.stage_done(slug, stage) -> bool`
  - `schema.validate_script(data: dict) -> list[str]` (returns list of error strings; empty = valid)

- [ ] **Step 1: Create the venv and pin deps**

Run:
```bash
cd /home/zain-ali/Documents/FFMPEG-YOUTUBE-AUTOMATION
python3 -m venv .venv
.venv/bin/pip install -q --upgrade pip
```
Create `requirements.txt`:
```
kokoro==0.9.4
soundfile==0.12.1
whisperx==3.1.5
pysbd==0.3.4
requests==2.32.3
pytest==8.3.4
```
Create `.gitignore`:
```
.venv/
__pycache__/
*.pyc
project/
.cache/
fixtures/cache/
```
Install test deps now (heavy ML deps installed in their own tasks):
```bash
.venv/bin/pip install -q pytest==8.3.4 requests==2.32.3 pysbd==0.3.4
```

- [ ] **Step 2: Write failing tests**

`tests/test_result.py`:
```python
from pipeline import result

def test_ok_shape():
    r = result.ok(path="a.wav")
    assert r == {"success": True, "error": None, "path": "a.wav"}

def test_err_shape():
    r = result.err("boom", stage="voice")
    assert r == {"success": False, "error": "boom", "stage": "voice"}

def test_run_catches_exception():
    def bad():
        raise ValueError("nope")
    r = result.run(bad)
    assert r["success"] is False
    assert "nope" in r["error"]

def test_run_passes_through():
    r = result.run(lambda: result.ok(n=1))
    assert r == {"success": True, "error": None, "n": 1}
```

`tests/test_manifest.py`:
```python
from pipeline import manifest

def test_init_and_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = manifest.init("demo")
    assert m["slug"] == "demo"
    assert m["stages"]["voice"]["status"] == "pending"
    assert manifest.load("demo")["slug"] == "demo"

def test_project_dir_creates_subdirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = manifest.project_dir("demo")
    assert (d / "audio").is_dir()
    assert (d / "media").is_dir()
    assert (d / "out").is_dir()

def test_set_stage_and_done(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest.init("demo")
    manifest.set_stage("demo", "voice", status="done", artifact="audio/voiceover.wav")
    assert manifest.stage_done("demo", "voice") is True
    assert manifest.stage_done("demo", "media") is False
    assert manifest.load("demo")["stages"]["voice"]["artifact"] == "audio/voiceover.wav"
```

`tests/test_schema.py`:
```python
import json
from pipeline import schema

def test_valid_fixture():
    data = json.load(open("fixtures/script.json"))
    assert schema.validate_script(data) == []

def test_missing_hook():
    errs = schema.validate_script({"slug": "x", "beats": []})
    assert any("hook" in e for e in errs)

def test_beat_requires_keywords():
    bad = {"slug": "x", "title": "t", "hook": "h", "outro": "o", "cta": "c",
           "beats": [{"id": 1, "narration": "n", "b_roll_keywords": []}]}
    errs = schema.validate_script(bad)
    assert any("b_roll_keywords" in e for e in errs)
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pipeline'`.

- [ ] **Step 4: Implement the package**

`pipeline/__init__.py`:
```python
```

`pipeline/result.py`:
```python
import json


def ok(**fields):
    return {"success": True, "error": None, **fields}


def err(message, **fields):
    return {"success": False, "error": str(message), **fields}


def run(fn):
    try:
        r = fn()
    except Exception as exc:  # noqa: BLE001 - scripts must never raise to caller
        r = err(str(exc))
    print(json.dumps(r))
    return r
```

`pipeline/manifest.py`:
```python
import json
from datetime import datetime, timezone
from pathlib import Path

STAGES = ("voice", "media", "music", "captions", "stitch")


def project_dir(slug, root="project"):
    d = Path(root) / slug
    for sub in ("", "audio", "media", "out"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


def _manifest_path(slug, root="project"):
    return project_dir(slug, root) / "manifest.json"


def init(slug, root="project"):
    data = {
        "slug": slug,
        "created": datetime.now(timezone.utc).isoformat(),
        "stages": {s: {"status": "pending"} for s in STAGES},
    }
    save(slug, data, root)
    return data


def load(slug, root="project"):
    return json.loads(_manifest_path(slug, root).read_text())


def save(slug, data, root="project"):
    _manifest_path(slug, root).write_text(json.dumps(data, indent=2))


def set_stage(slug, stage, root="project", **fields):
    data = load(slug, root)
    data["stages"].setdefault(stage, {}).update(fields)
    save(slug, data, root)
    return data


def stage_done(slug, stage, root="project"):
    try:
        return load(slug, root)["stages"].get(stage, {}).get("status") == "done"
    except FileNotFoundError:
        return False
```

`pipeline/schema.py`:
```python
REQUIRED_TOP = ("slug", "title", "hook", "beats", "outro", "cta")


def validate_script(data):
    errs = []
    if not isinstance(data, dict):
        return ["script.json must be an object"]
    for key in REQUIRED_TOP:
        if key not in data or data[key] in (None, ""):
            errs.append(f"missing required field: {key}")
    beats = data.get("beats")
    if not isinstance(beats, list) or not beats:
        errs.append("beats must be a non-empty array")
        return errs
    for i, beat in enumerate(beats):
        if not beat.get("narration"):
            errs.append(f"beat[{i}] missing narration")
        kws = beat.get("b_roll_keywords")
        if not isinstance(kws, list) or not kws:
            errs.append(f"beat[{i}] b_roll_keywords must be a non-empty array")
    return errs
```

`fixtures/script.json`:
```json
{
  "slug": "demo",
  "title": "Three Surprising Facts About Octopuses",
  "hook": "Octopuses have three hearts and blue blood.",
  "beats": [
    {
      "id": 1,
      "narration": "An octopus has three hearts. Two pump blood to the gills, one to the body.",
      "on_screen_text": "3 hearts",
      "b_roll_keywords": ["octopus", "ocean"]
    },
    {
      "id": 2,
      "narration": "Their blood is blue because it uses copper, not iron, to carry oxygen.",
      "on_screen_text": "blue blood",
      "b_roll_keywords": ["octopus underwater", "deep sea"]
    }
  ],
  "outro": "Nature is stranger than fiction.",
  "cta": "Follow for one weird fact a day."
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS (all tests in the three files).

- [ ] **Step 6: Commit**

```bash
git add pipeline/ tests/ fixtures/script.json requirements.txt .gitignore
git commit -m "feat: shared pipeline package (result, manifest, schema)"
```

---

### Task 2: `yt-voice` skill — Kokoro TTS per beat

**Files:**
- Create: `.claude/skills/yt-voice/SKILL.md`
- Create: `.claude/skills/yt-voice/scripts/generate_voice.py`
- Test: `tests/test_voice.py`

**Interfaces:**
- Consumes: `pipeline.result`, `pipeline.manifest`, `pipeline.schema`; reads `project/<slug>/script.json`.
- Produces:
  - `generate_voice.plan_beats(script: dict) -> list[dict]` → `[{"id", "text"}]` (hook + each beat narration + outro, in order; skips empty).
  - `generate_voice.concat_timings(durations: list[float]) -> list[dict]` → `[{"id", "start", "end"}]` cumulative.
  - CLI: `python generate_voice.py <slug>` → writes `audio/voiceover.wav`, sets manifest stage `voice` with `beat_timings`, prints result envelope.

- [ ] **Step 1: Install voice deps + system espeak-ng**

Run:
```bash
sudo apt-get install -y espeak-ng
.venv/bin/pip install -q kokoro==0.9.4 soundfile==0.12.1
```
Expected: `espeak-ng --version` prints a version; pip install succeeds.

- [ ] **Step 2: Write failing tests for the pure functions**

`tests/test_voice.py`:
```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "generate_voice",
    pathlib.Path(".claude/skills/yt-voice/scripts/generate_voice.py"))
gv = importlib.util.module_from_spec(spec); spec.loader.exec_module(gv)

def test_plan_beats_orders_hook_first():
    script = {"hook": "H", "outro": "O", "cta": "C",
              "beats": [{"id": 1, "narration": "A", "b_roll_keywords": ["k"]},
                        {"id": 2, "narration": "B", "b_roll_keywords": ["k"]}]}
    plan = gv.plan_beats(script)
    assert [p["text"] for p in plan] == ["H", "A", "B", "O"]

def test_plan_beats_skips_empty():
    script = {"hook": "H", "outro": "", "cta": "C",
              "beats": [{"id": 1, "narration": "A", "b_roll_keywords": ["k"]}]}
    assert [p["text"] for p in gv.plan_beats(script)] == ["H", "A"]

def test_concat_timings_cumulative():
    t = gv.concat_timings([1.0, 2.0, 0.5])
    assert t == [
        {"id": 0, "start": 0.0, "end": 1.0},
        {"id": 1, "start": 1.0, "end": 3.0},
        {"id": 2, "start": 3.0, "end": 3.5},
    ]
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_voice.py -v`
Expected: FAIL — file/module not found.

- [ ] **Step 4: Implement `generate_voice.py`**

`.claude/skills/yt-voice/scripts/generate_voice.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from pipeline import result, manifest, schema  # noqa: E402

VOICE = "af_heart"
LANG = "a"
SR = 24000


def plan_beats(script):
    items = []
    if script.get("hook"):
        items.append({"id": 0, "text": script["hook"]})
    for beat in script.get("beats", []):
        if beat.get("narration"):
            items.append({"id": beat["id"], "text": beat["narration"]})
    if script.get("outro"):
        items.append({"id": -1, "text": script["outro"]})
    return items


def concat_timings(durations):
    out, t = [], 0.0
    for i, d in enumerate(durations):
        out.append({"id": i, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def _synthesize(slug):
    import json
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    d = manifest.project_dir(slug)
    script = json.loads((d / "script.json").read_text())
    errs = schema.validate_script(script)
    if errs:
        return result.err("invalid script.json: " + "; ".join(errs))
    if manifest.stage_done(slug, "voice") and "--force" not in sys.argv:
        return result.ok(skipped=True, stage="voice")

    plan = plan_beats(script)
    pipe = KPipeline(lang_code=LANG)
    chunks, durations = [], []
    for item in plan:
        audio = np.concatenate([g.audio for g in pipe(item["text"], voice=VOICE)])
        chunks.append(audio)
        durations.append(len(audio) / SR)
    full = np.concatenate(chunks)
    out_path = d / "audio" / "voiceover.wav"
    sf.write(out_path, full, SR)

    timings = concat_timings(durations)
    manifest.set_stage(slug, "voice", status="done",
                       artifact="audio/voiceover.wav", beat_timings=timings)
    return result.ok(artifact=str(out_path), beats=len(plan),
                     duration=round(sum(durations), 3))


if __name__ == "__main__":
    slug = sys.argv[1]
    result.run(lambda: _synthesize(slug))
```

- [ ] **Step 5: Run pure-function tests**

Run: `.venv/bin/pytest tests/test_voice.py -v`
Expected: PASS.

- [ ] **Step 6: Manual end-to-end check on the fixture**

Run:
```bash
mkdir -p project/demo && cp fixtures/script.json project/demo/script.json
.venv/bin/python .claude/skills/yt-voice/scripts/generate_voice.py demo
```
Expected: stdout JSON `"success": true`; `project/demo/audio/voiceover.wav` exists; `ffprobe -i project/demo/audio/voiceover.wav` shows an audio stream.

- [ ] **Step 7: Write SKILL.md**

`.claude/skills/yt-voice/SKILL.md`:
```markdown
---
name: yt-voice
description: Generate voiceover audio from a video project's script.json using local Kokoro-82M TTS. Use when a project folder has a validated script.json and needs narration (audio/voiceover.wav) before media/captions/stitch stages.
---

# yt-voice

Generates `audio/voiceover.wav` for `project/<slug>/` from `script.json` using Kokoro-82M (Apache-2.0, CPU).

## Run
`python .claude/skills/yt-voice/scripts/generate_voice.py <slug> [--force]`

The script reads `project/<slug>/script.json`, synthesizes the hook + each beat + outro
with preset voice `af_heart`, concatenates to one 24kHz WAV, and records per-beat
`beat_timings` into `manifest.json`. Output is a single JSON envelope on stdout.

Requires system `espeak-ng` and the project venv (`kokoro`, `soundfile`).
Idempotent: skips if stage `voice` is already `done` unless `--force`.
```

- [ ] **Step 8: Commit**

```bash
git add .claude/skills/yt-voice/ tests/test_voice.py
git commit -m "feat: yt-voice skill (Kokoro TTS per beat)"
```

---

### Task 3: `yt-media` skill — Pexels/Pixabay fetch + cache + backoff + license log

**Files:**
- Create: `.claude/skills/yt-media/SKILL.md`
- Create: `.claude/skills/yt-media/scripts/fetch_media.py`
- Test: `tests/test_media.py`

**Interfaces:**
- Consumes: `pipeline.result`, `pipeline.manifest`; reads `script.json`.
- Produces:
  - `fetch_media.pick_pexels_video(resp: dict) -> dict|None` → `{"url", "license"}` from a Pexels videos response (highest-res ≤1920 file).
  - `fetch_media.pick_pexels_photo(resp: dict) -> dict|None` → `{"url", "license"}`.
  - `fetch_media.pick_pixabay(resp: dict, kind: str) -> dict|None` → `{"url", "license"}` for `kind in {"video","photo","music"}`.
  - `fetch_media.backoff_delays(n: int, base=1.0, cap=30.0) -> list[float]` → exponential `[1,2,4,...]` capped.
  - `fetch_media.cache_key(url: str) -> str` (sha1 hex).
  - CLI: `python fetch_media.py <slug>` → downloads one asset per beat to `media/`, one music track to `audio/music.mp3`, logs sources+licenses to manifest stages `media` and `music`.

- [ ] **Step 1: Write failing tests for pure parsers/helpers**

`tests/test_media.py`:
```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "fetch_media",
    pathlib.Path(".claude/skills/yt-media/scripts/fetch_media.py"))
fm = importlib.util.module_from_spec(spec); spec.loader.exec_module(fm)

def test_pick_pexels_video_picks_largest_within_cap():
    resp = {"videos": [{"video_files": [
        {"width": 640, "height": 360, "link": "lo.mp4"},
        {"width": 1920, "height": 1080, "link": "hi.mp4"},
        {"width": 3840, "height": 2160, "link": "uhd.mp4"},
    ]}]}
    pick = fm.pick_pexels_video(resp)
    assert pick["url"] == "hi.mp4"
    assert "pexels" in pick["license"].lower()

def test_pick_pexels_video_none_when_empty():
    assert fm.pick_pexels_video({"videos": []}) is None

def test_pick_pixabay_photo():
    resp = {"hits": [{"largeImageURL": "p.jpg"}]}
    pick = fm.pick_pixabay(resp, "photo")
    assert pick["url"] == "p.jpg"
    assert "pixabay" in pick["license"].lower()

def test_backoff_is_exponential_and_capped():
    assert fm.backoff_delays(5, base=1.0, cap=8.0) == [1.0, 2.0, 4.0, 8.0, 8.0]

def test_cache_key_stable():
    assert fm.cache_key("http://x/y") == fm.cache_key("http://x/y")
    assert fm.cache_key("a") != fm.cache_key("b")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_media.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `fetch_media.py`**

`.claude/skills/yt-media/scripts/fetch_media.py`:
```python
import hashlib
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from pipeline import result, manifest  # noqa: E402

PEXELS_LICENSE = "Pexels License (free commercial, no attribution)"
PIXABAY_LICENSE = "Pixabay Content License (free commercial)"
CACHE_DIR = Path(".cache/media")


def pick_pexels_video(resp, max_w=1920):
    vids = resp.get("videos") or []
    if not vids:
        return None
    files = sorted(vids[0].get("video_files", []),
                   key=lambda f: f.get("width", 0))
    eligible = [f for f in files if f.get("width", 0) <= max_w] or files
    return {"url": eligible[-1]["link"], "license": PEXELS_LICENSE}


def pick_pexels_photo(resp):
    photos = resp.get("photos") or []
    if not photos:
        return None
    return {"url": photos[0]["src"]["large2x"], "license": PEXELS_LICENSE}


def pick_pixabay(resp, kind):
    hits = resp.get("hits") or []
    if not hits:
        return None
    h = hits[0]
    if kind == "photo":
        url = h.get("largeImageURL")
    elif kind == "video":
        url = h["videos"]["large"]["url"]
    else:  # music
        url = h.get("download") or h.get("audio")
    return {"url": url, "license": PIXABAY_LICENSE} if url else None


def backoff_delays(n, base=1.0, cap=30.0):
    return [min(base * (2 ** i), cap) for i in range(n)]


def cache_key(url):
    return hashlib.sha1(url.encode()).hexdigest()


def _get_json(url, headers=None, params=None, retries=5):
    import requests
    for delay in [0.0] + backoff_delays(retries):
        if delay:
            time.sleep(delay)
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=30)
        if r.status_code == 429:
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"rate-limited after {retries} retries: {url}")


def _download(url, dest):
    import requests
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / cache_key(url)
    if not cached.exists():
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        cached.write_bytes(r.content)
    dest.write_bytes(cached.read_bytes())


def _fetch(slug):
    pexels_key = os.environ.get("PEXELS_API_KEY")
    pixabay_key = os.environ.get("PIXABAY_API_KEY")
    if not pexels_key and not pixabay_key:
        return result.err("set PEXELS_API_KEY and/or PIXABAY_API_KEY")
    if manifest.stage_done(slug, "media") and "--force" not in sys.argv:
        return result.ok(skipped=True, stage="media")

    d = manifest.project_dir(slug)
    script = json.loads((d / "script.json").read_text())
    assets = []
    for beat in script["beats"]:
        kw = " ".join(beat["b_roll_keywords"])
        pick = None
        if pexels_key:
            resp = _get_json("https://api.pexels.com/videos/search",
                             headers={"Authorization": pexels_key},
                             params={"query": kw, "per_page": 1})
            pick = pick_pexels_video(resp)
        if not pick and pixabay_key:
            resp = _get_json("https://pixabay.com/api/videos/",
                             params={"key": pixabay_key, "q": kw, "per_page": 3})
            pick = pick_pixabay(resp, "video")
        if not pick:
            return result.err(f"no media for beat {beat['id']} ({kw})")
        ext = ".mp4" if pick["url"].endswith(("mp4", "/")) or "video" in pick["url"] else ".jpg"
        dest = d / "media" / f"beat_{beat['id']}{ext}"
        _download(pick["url"], dest)
        assets.append({"beat": beat["id"], "path": str(dest.relative_to(d)),
                       "source": "pexels" if pexels_key else "pixabay",
                       "license": pick["license"]})

    music = None
    if pixabay_key:
        resp = _get_json("https://pixabay.com/api/",
                         params={"key": pixabay_key, "q": "background ambient",
                                 "per_page": 3, "category": "music"})
    manifest.set_stage(slug, "media", status="done", assets=assets)
    manifest.set_stage(slug, "music", status="done",
                       path="audio/music.mp3" if music else None,
                       source="pixabay", license=PIXABAY_LICENSE)
    return result.ok(assets=len(assets))


if __name__ == "__main__":
    slug = sys.argv[1]
    result.run(lambda: _fetch(slug))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_media.py -v`
Expected: PASS.

- [ ] **Step 5: Write SKILL.md**

`.claude/skills/yt-media/SKILL.md`:
```markdown
---
name: yt-media
description: Fetch royalty-free b-roll and music for a video project from Pexels and Pixabay, keyed off each script beat's b_roll_keywords. Use after script.json exists and before captions/stitch. Downloads assets locally and logs every license into manifest.json.
---

# yt-media

Fetches one b-roll asset per beat (Pexels primary, Pixabay fallback) plus one Pixabay
CC0 music track into `project/<slug>/media/` and `audio/`. Downloads locally (no
hotlinking), caches for reuse, backs off on HTTP 429, and logs source+license to
`manifest.json`.

## Run
`PEXELS_API_KEY=... PIXABAY_API_KEY=... python .claude/skills/yt-media/scripts/fetch_media.py <slug> [--force]`

Only Pexels/Pixabay are allowed sources; music is Pixabay CC0. Idempotent: skips if
stage `media` is `done` unless `--force`.
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/yt-media/ tests/test_media.py
git commit -m "feat: yt-media skill (Pexels/Pixabay fetch + cache + backoff)"
```

---

### Task 4: `yt-captions` skill — WhisperX + PySBD → styled ASS

**Files:**
- Create: `.claude/skills/yt-captions/SKILL.md`
- Create: `.claude/skills/yt-captions/scripts/generate_captions.py`
- Test: `tests/test_captions.py`

**Interfaces:**
- Consumes: `pipeline.result`, `pipeline.manifest`; reads `audio/voiceover.wav`.
- Produces:
  - `generate_captions.group_words(words: list[dict], max_chars=42) -> list[dict]` → cues `{"start","end","text"}` from word dicts `{"word","start","end"}`, splitting at PySBD sentence boundaries and at `max_chars`.
  - `generate_captions.to_ass(cues: list[dict]) -> str` → full ASS document string with a styled `Default` style.
  - `generate_captions.fmt_ts(seconds: float) -> str` → ASS `H:MM:SS.cs`.
  - CLI: `python generate_captions.py <slug>` → writes `captions.ass`, sets stage `captions`.

- [ ] **Step 1: Write failing tests for the pure functions**

`tests/test_captions.py`:
```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "generate_captions",
    pathlib.Path(".claude/skills/yt-captions/scripts/generate_captions.py"))
gc = importlib.util.module_from_spec(spec); spec.loader.exec_module(gc)

def test_fmt_ts():
    assert gc.fmt_ts(0) == "0:00:00.00"
    assert gc.fmt_ts(3661.5) == "1:01:01.50"

def test_group_words_splits_on_sentence():
    words = [{"word": w, "start": i, "end": i + 1}
             for i, w in enumerate(["Hello", "there.", "New", "one."])]
    cues = gc.group_words(words, max_chars=100)
    assert len(cues) == 2
    assert cues[0]["text"] == "Hello there."
    assert cues[0]["start"] == 0 and cues[0]["end"] == 2

def test_group_words_splits_on_max_chars():
    words = [{"word": "ab", "start": i, "end": i + 1} for i in range(5)]
    cues = gc.group_words(words, max_chars=5)
    assert all(len(c["text"]) <= 5 for c in cues)
    assert len(cues) >= 2

def test_to_ass_has_header_and_dialogue():
    ass = gc.to_ass([{"start": 0.0, "end": 1.0, "text": "Hi"}])
    assert "[Script Info]" in ass and "[V4+ Styles]" in ass
    assert "Dialogue:" in ass and "Hi" in ass
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_captions.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `generate_captions.py`**

`.claude/skills/yt-captions/scripts/generate_captions.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from pipeline import result, manifest  # noqa: E402

ASS_HEADER = """[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,90,&H00FFFFFF,&H00000000,&H00000000,1,1,4,2,2,60,60,200,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def fmt_ts(seconds):
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def group_words(words, max_chars=42):
    import pysbd
    seg = pysbd.Segmenter(language="en", clean=False)
    full = " ".join(w["word"].strip() for w in words)
    sentences = [s.strip() for s in seg.segment(full) if s.strip()]

    cues, idx = [], 0
    for sentence in sentences:
        n = len(sentence.split())
        group = words[idx:idx + n]
        idx += n
        if not group:
            continue
        cur, cur_start = [], group[0]["start"]
        for w in group:
            tentative = " ".join([*[c["word"].strip() for c in cur], w["word"].strip()])
            if cur and len(tentative) > max_chars:
                cues.append({"start": cur_start, "end": cur[-1]["end"],
                             "text": " ".join(c["word"].strip() for c in cur)})
                cur, cur_start = [w], w["start"]
            else:
                cur.append(w)
        if cur:
            cues.append({"start": cur_start, "end": cur[-1]["end"],
                         "text": " ".join(c["word"].strip() for c in cur)})
    return cues


def to_ass(cues):
    lines = [ASS_HEADER]
    for c in cues:
        lines.append(
            f"Dialogue: 0,{fmt_ts(c['start'])},{fmt_ts(c['end'])},Default,,0,0,0,,{c['text']}")
    return "\n".join(lines) + "\n"


def _transcribe(slug):
    import whisperx
    if manifest.stage_done(slug, "captions") and "--force" not in sys.argv:
        return result.ok(skipped=True, stage="captions")
    d = manifest.project_dir(slug)
    wav = d / "audio" / "voiceover.wav"
    model = whisperx.load_model("base", device="cpu", compute_type="int8")
    audio = whisperx.load_audio(str(wav))
    tx = model.transcribe(audio, batch_size=4)
    align_model, meta = whisperx.load_align_model(language_code="en", device="cpu")
    aligned = whisperx.align(tx["segments"], align_model, meta, audio, "cpu")
    words = [{"word": w["word"], "start": w.get("start", 0.0), "end": w.get("end", 0.0)}
             for seg in aligned["segments"] for w in seg.get("words", [])
             if w.get("start") is not None]
    cues = group_words(words)
    (d / "captions.ass").write_text(to_ass(cues))
    manifest.set_stage(slug, "captions", status="done", artifact="captions.ass",
                       cues=len(cues))
    return result.ok(cues=len(cues))


if __name__ == "__main__":
    slug = sys.argv[1]
    result.run(lambda: _transcribe(slug))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_captions.py -v`
Expected: PASS.

- [ ] **Step 5: Write SKILL.md**

`.claude/skills/yt-captions/SKILL.md`:
```markdown
---
name: yt-captions
description: Generate styled, readable ASS captions for a video project from its voiceover.wav using WhisperX word-level timestamps and PySBD sentence segmentation. Use after yt-voice and before yt-stitch.
---

# yt-captions

Transcribes `audio/voiceover.wav` with WhisperX (CPU), aligns to word-level timestamps,
segments into readable sentence-bounded cues with PySBD (max line width), and writes a
styled `captions.ass` (centered, bold, white with outline).

## Run
`python .claude/skills/yt-captions/scripts/generate_captions.py <slug> [--force]`

Idempotent: skips if stage `captions` is `done` unless `--force`.
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/yt-captions/ tests/test_captions.py
git commit -m "feat: yt-captions skill (WhisperX + PySBD -> ASS)"
```

---

### Task 5: `yt-stitch` skill — FFmpeg, both aspect ratios

**Files:**
- Create: `.claude/skills/yt-stitch/SKILL.md`
- Create: `.claude/skills/yt-stitch/scripts/stitch_video.py`
- Test: `tests/test_stitch.py`

**Interfaces:**
- Consumes: `pipeline.result`, `pipeline.manifest`; reads manifest `voice.beat_timings`, `media.assets`, `music.path`, `captions.ass`.
- Produces:
  - `stitch_video.scale_pad_filter(aspect: str) -> str` → FFmpeg scale+crop+pad chain for `"9x16"` (1080×1920) or `"16x9"` (1920×1080).
  - `stitch_video.zoompan_clause(duration: float, fps=30) -> str` → Ken Burns `zoompan` for a still.
  - `stitch_video.build_command(assets, timings, music, captions, out_path, aspect) -> list[str]` → full `ffmpeg` argv list.
  - CLI: `python stitch_video.py <slug>` → renders `out/video_9x16.mp4` and `out/video_16x9.mp4`, sets stage `stitch`.

- [ ] **Step 1: Write failing tests for the command builders**

`tests/test_stitch.py`:
```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "stitch_video",
    pathlib.Path(".claude/skills/yt-stitch/scripts/stitch_video.py"))
sv = importlib.util.module_from_spec(spec); spec.loader.exec_module(sv)

def test_scale_pad_9x16():
    f = sv.scale_pad_filter("9x16")
    assert "1080" in f and "1920" in f

def test_scale_pad_16x9():
    f = sv.scale_pad_filter("16x9")
    assert "1920" in f and "1080" in f

def test_zoompan_uses_duration():
    clause = sv.zoompan_clause(2.0, fps=30)
    assert "zoompan" in clause and "d=60" in clause  # 2.0s * 30fps

def test_build_command_includes_outputs_and_format():
    cmd = sv.build_command(
        assets=[{"beat": 1, "path": "media/beat_1.jpg"}],
        timings=[{"id": 0, "start": 0.0, "end": 2.0}],
        music="audio/music.mp3", captions="captions.ass",
        out_path="out/video_9x16.mp4", aspect="9x16")
    assert cmd[0] == "ffmpeg"
    assert "out/video_9x16.mp4" in cmd
    assert "yuv420p" in cmd
    assert "+faststart" in cmd
    assert any("ass=" in str(c) for c in cmd)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv/bin/pytest tests/test_stitch.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `stitch_video.py`**

`.claude/skills/yt-stitch/scripts/stitch_video.py`:
```python
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from pipeline import result, manifest  # noqa: E402

DIMS = {"9x16": (1080, 1920), "16x9": (1920, 1080)}


def scale_pad_filter(aspect):
    w, h = DIMS[aspect]
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1")


def zoompan_clause(duration, fps=30):
    frames = int(round(duration * fps))
    return (f"zoompan=z='min(zoom+0.0015,1.15)':d={frames}:"
            f"s=1280x720:fps={fps}")


def _is_image(path):
    return str(path).lower().endswith((".jpg", ".jpeg", ".png"))


def build_command(assets, timings, music, captions, out_path, aspect):
    w, h = DIMS[aspect]
    by_beat = {a["beat"]: a for a in assets}
    inputs, filters, concat_parts = [], [], []
    body = [t for t in timings if t["id"] not in (0, -1)] or timings
    for idx, t in enumerate(body):
        dur = round(t["end"] - t["start"], 3)
        asset = by_beat.get(t["id"]) or assets[idx % len(assets)]
        path = asset["path"]
        if _is_image(path):
            inputs += ["-loop", "1", "-t", str(dur), "-i", path]
            vf = f"{zoompan_clause(dur)},{scale_pad_filter(aspect)}"
        else:
            inputs += ["-t", str(dur), "-i", path]
            vf = scale_pad_filter(aspect)
        filters.append(f"[{idx}:v]{vf},setpts=PTS-STARTPTS[v{idx}]")
        concat_parts.append(f"[v{idx}]")
    n = len(body)
    vconcat = "".join(concat_parts) + f"concat=n={n}:v=1:a=0[vbg]"
    cap = f"[vbg]ass={captions}[vout]"

    voice_idx = len(body)
    inputs += ["-i", "audio/voiceover.wav"]
    audio_chain = f"[{voice_idx}:a]"
    if music:
        music_idx = voice_idx + 1
        inputs += ["-i", music]
        audio_chain = (
            f"[{music_idx}:a]volume=0.3[bg];"
            f"[bg][{voice_idx}:a]sidechaincompress=threshold=0.05:ratio=8[aout]")
        amap = "[aout]"
    else:
        amap = f"[{voice_idx}:a]"

    fc = ";".join([*filters, vconcat, cap] +
                  ([audio_chain] if music else []))
    cmd = ["ffmpeg", "-y", *inputs,
           "-filter_complex", fc,
           "-map", "[vout]", "-map", amap,
           "-c:v", "libx264", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-shortest",
           "-movflags", "+faststart", out_path]
    return cmd


def _render(slug):
    if manifest.stage_done(slug, "stitch") and "--force" not in sys.argv:
        return result.ok(skipped=True, stage="stitch")
    d = manifest.project_dir(slug)
    m = manifest.load(slug)
    timings = m["stages"]["voice"]["beat_timings"]
    assets = m["stages"]["media"]["assets"]
    music = m["stages"]["music"].get("path")
    outputs = []
    for aspect in ("9x16", "16x9"):
        out_rel = f"out/video_{aspect}.mp4"
        cmd = build_command(assets, timings, music, "captions.ass", out_rel, aspect)
        subprocess.run(cmd, cwd=d, check=True, capture_output=True)
        outputs.append(out_rel)
    manifest.set_stage(slug, "stitch", status="done", outputs=outputs)
    return result.ok(outputs=outputs)


if __name__ == "__main__":
    slug = sys.argv[1]
    result.run(lambda: _render(slug))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/pytest tests/test_stitch.py -v`
Expected: PASS.

- [ ] **Step 5: Write SKILL.md**

`.claude/skills/yt-stitch/SKILL.md`:
```markdown
---
name: yt-stitch
description: Assemble the final videos for a project with pure FFmpeg — timed b-roll with Ken Burns, voiceover, music ducked under narration, and burned ASS captions — rendering both 9:16 and 16:9 MP4s. Use as the final stage after voice, media, and captions are done.
---

# yt-stitch

Reads `manifest.json` (beat timings, assets, music) and `captions.ass`, then renders
`out/video_9x16.mp4` (1080×1920) and `out/video_16x9.mp4` (1920×1080) with pure FFmpeg:
`zoompan` Ken Burns on stills, `sidechaincompress` to duck music under the voiceover,
burned ASS captions, `yuv420p` + `+faststart`.

## Run
`python .claude/skills/yt-stitch/scripts/stitch_video.py <slug> [--force]`

Idempotent: skips if stage `stitch` is `done` unless `--force`.
```

- [ ] **Step 6: Commit**

```bash
git add .claude/skills/yt-stitch/ tests/test_stitch.py
git commit -m "feat: yt-stitch skill (pure FFmpeg, both aspect ratios)"
```

---

### Task 6: `yt-make` orchestrator + end-to-end smoke test

**Files:**
- Create: `.claude/skills/yt-make/SKILL.md`
- Create: `tests/test_smoke.py`

**Interfaces:**
- Consumes: all four stage scripts via subprocess; `pipeline.manifest`, `pipeline.schema`.
- Produces: the orchestration contract documented in SKILL.md (no new Python module).

- [ ] **Step 1: Write the end-to-end smoke test (uses mocked network for media)**

`tests/test_smoke.py`:
```python
import json, os, subprocess, sys, pathlib, shutil
import pytest

ROOT = pathlib.Path(".").resolve()
VENV_PY = ROOT / ".venv/bin/python"

needs_models = pytest.mark.skipif(
    os.environ.get("RUN_SMOKE") != "1",
    reason="set RUN_SMOKE=1 to run the heavy end-to-end smoke test")

@needs_models
def test_spine_end_to_end(tmp_path):
    # Arrange: fresh project from fixture
    slug = "smoke"
    proj = ROOT / "project" / slug
    if proj.exists():
        shutil.rmtree(proj)
    (proj / "").mkdir(parents=True, exist_ok=True)
    proj.mkdir(parents=True, exist_ok=True)
    (proj).mkdir(exist_ok=True)
    shutil.copy(ROOT / "fixtures/script.json", proj / "script.json")

    def run(script):
        r = subprocess.run([str(VENV_PY), script, slug],
                           cwd=ROOT, capture_output=True, text=True)
        out = json.loads(r.stdout.strip().splitlines()[-1])
        assert out["success"], out
        return out

    run(".claude/skills/yt-voice/scripts/generate_voice.py")
    run(".claude/skills/yt-media/scripts/fetch_media.py")
    run(".claude/skills/yt-captions/scripts/generate_captions.py")
    run(".claude/skills/yt-stitch/scripts/stitch_video.py")

    for aspect, dims in (("9x16", "1080x1920"), ("16x9", "1920x1080")):
        out = proj / "out" / f"video_{aspect}.mp4"
        assert out.exists() and out.stat().st_size > 0
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries",
             "stream=codec_type,width,height", "-of", "csv", str(out)],
            capture_output=True, text=True).stdout
        assert "video" in probe and "audio" in probe

    m = json.loads((proj / "manifest.json").read_text())
    for a in m["stages"]["media"]["assets"]:
        assert a["license"], "every asset must have a logged license"
```

- [ ] **Step 2: Run the fast suite (smoke skipped by default)**

Run: `.venv/bin/pytest tests/ -v`
Expected: PASS for all unit tests; `test_spine_end_to_end` SKIPPED.

- [ ] **Step 3: Run the full smoke test once manually**

Run:
```bash
RUN_SMOKE=1 PEXELS_API_KEY=$PEXELS_API_KEY PIXABAY_API_KEY=$PIXABAY_API_KEY \
  .venv/bin/pytest tests/test_smoke.py -v
```
Expected: PASS — both MP4s exist, each has video+audio streams, every media asset has a license.

- [ ] **Step 4: Write the orchestrator SKILL.md (with the approval gate)**

`.claude/skills/yt-make/SKILL.md`:
```markdown
---
name: yt-make
description: Orchestrate the faceless YouTube render spine end-to-end for a project slug — validate the script, pause for human approval, then run voice, media, captions, and stitch in order. Use when a project/<slug>/script.json is ready to become finished 9:16 and 16:9 videos.
---

# yt-make

Runs the spine for `project/<slug>/` in order. Claude is the orchestrator: it runs each
script, parses the JSON envelope, and only proceeds when `success` is true.

## Procedure
1. **Validate** `project/<slug>/script.json` with `pipeline.schema.validate_script`.
   If errors, stop and report them.
2. **Approval gate (REQUIRED):** show the user the hook and beat list from `script.json`
   and ask for explicit approval before any rendering. Do not proceed without it.
3. Run `yt-voice` → check `success`.
4. Run `yt-media` (needs `PEXELS_API_KEY`/`PIXABAY_API_KEY`) → check `success`.
5. Run `yt-captions` → check `success`.
6. Run `yt-stitch` → check `success`.
7. Report `out/video_9x16.mp4` and `out/video_16x9.mp4`.

Each stage is idempotent; re-running resumes from the first not-`done` stage. Pass
`--force` to a stage to redo it.

## Run a stage
`python .claude/skills/<stage>/scripts/<script>.py <slug> [--force]`
```

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/yt-make/ tests/test_smoke.py
git commit -m "feat: yt-make orchestrator + end-to-end smoke test"
```

---

## Self-Review

**Spec coverage:**
- Folder/manifest/script contract → Task 1 ✓
- Kokoro TTS, single preset voice, beat timings → Task 2 ✓
- Pexels/Pixabay only, download-local, cache, 429 backoff, license log → Task 3 ✓
- WhisperX + PySBD + styled ASS → Task 4 ✓
- Pure FFmpeg, zoompan, sidechaincompress, both aspect ratios, yuv420p/+faststart → Task 5 ✓
- Orchestrator + approval gate + idempotency + smoke test → Task 6 ✓
- Result envelope, never-raise contract → Task 1 + used by every script ✓
- espeak-ng install → Task 2 Step 1 ✓
- Deferred (discover/script) → correctly out of scope, no tasks ✓

**Type consistency:** `manifest.set_stage(slug, stage, **fields)`, `result.ok/err`,
`beat_timings` (list of `{id,start,end}`), `assets` (list of `{beat,path,source,license}`),
`music.path` — names used identically across Tasks 2–6 ✓.

**Placeholder scan:** no TBD/TODO; every code step shows full code; commands have expected
output ✓.

**Known implementation caveats (resolve during execution, not blockers):**
- Pexels photo `src` key is `large2x`; verify against live API response shape in Task 3 Step 6.
- Pixabay music endpoint/field (`download`/`audio`) varies; the music track is optional —
  stitch tolerates `music=None`. Confirm a working music query during Task 3.
- WhisperX model size `base` chosen for CPU speed; bump to `small` only if alignment quality is poor.
```

