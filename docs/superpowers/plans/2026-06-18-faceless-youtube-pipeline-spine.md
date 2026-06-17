<!-- /autoplan restore point: /home/zain-ali/.gstack/projects/FFMPEG-YOUTUBE-AUTOMATION/master-autoplan-restore-20260618-003435.md -->
# Faceless YouTube Pipeline — Spine v1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn one hand-authored `script.json` into a captioned video in both 9:16 and 16:9, on a CPU-only Linux box, using only free/local tooling — and ship it down a **monetization-oriented path** (YouTube ad revenue is the stated objective, facts/educational niche).

**Objective (premise gate, confirmed):** AD REVENUE / YPP monetization. This raises YouTube's July-2025 "inauthentic / mass-produced content" policy risk for templated faceless output, so three things are **first-class v1 scope, not afterthoughts**: (1) per-video differentiation (voice rotation, multi-candidate b-roll selection, motion variety), (2) a pre-publish Content-ID + license gate, (3) a publish + retention-feedback loop. The actual revenue levers (outlier topic discovery, high-retention scripts) live in the deferred discovery/script stages — the spine is built so they slot in without rework.

**Niche (confirmed):** **AI tools & productivity for professionals/business.** Chosen for the best RPM-vs-feasibility balance for a faceless automated channel: $10–25 est. RPM, fastest-growing + lower competition ("best new-channel entry point"), inherently transformative (testing/comparing tools clears the authenticity bar), recurring SaaS affiliate income, and **no YMYL accuracy liability**. Future-expansion niches (noted, not built now): **personal finance / money-explainer** (highest RPM $10–35+, biggest affiliate stack, but YMYL), **software/B2B-SaaS reviews** ($15–40 RPM, more production effort), **high-RPM storytelling** (betrayal/family-court ~$9–13 RPM, higher templating risk). Don't niche-hop before ~100 videos.

**Output strategy (confirmed):** **Long-form-first.** 16:9 long-form **8–20 min** (cross the 8:00 mid-roll threshold) is the primary product and the only path to the 4,000 watch-hours YPP bar — **Shorts-feed watch time does NOT count toward 4,000 hours**. 9:16 Shorts are **cut from the highest-retention long-form segments** as a subscriber/discovery feeder, not authored separately. (This reweights the earlier "render both equally" stance: long-form is primary; Shorts are derived.)

**Architecture:** A shared `pipeline/` Python package provides the result envelope, project-folder + manifest helpers, and `script.json` validation. Single-responsibility skills (`yt-voice`, `yt-media`, `yt-captions`, `yt-stitch`, `yt-guard`, `yt-publish`) each wrap one Python script that reads/writes a per-video project folder and returns a `{"success": bool, "error": ...}` JSON envelope. A `yt-make` orchestrator runs them in order behind a human approval gate on the script. Heavy/IO-bound work (Kokoro, WhisperX, FFmpeg, HTTP) sits in thin wrappers around pure, unit-tested core functions (command building, caption segmentation, API-response parsing, timeline math).

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
- **Monetization (YPP) constraints — first-class, never skipped:**
  - **Differentiation:** voice is selectable/rotatable per video (not hardcoded one voice); `yt-media` fetches ≥3 candidates per beat and selects, never blindly first hit; Ken Burns motion direction varies per clip. Identical-looking output across videos is the "repetitive content" signal that demonetizes.
  - **No silent media failure:** a beat with no usable stock asset falls back to a solid-color + `on_screen_text` card — it must NEVER hard-fail the whole render.
  - **Pre-publish gate is mandatory:** no video is considered publishable until `yt-guard` passes (every asset license logged + a Content-ID spot-check prompt).
  - **Measurement:** every published video gets a retention-notes record so topic/hook performance is learnable.

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

### Amendments from CEO review (accepted scope — monetization path)

These fold into the tasks above during implementation. Each is TDD'd like any other step.

**A1 (Task 2 `yt-voice`) — voice rotation.** Replace the hardcoded `VOICE = "af_heart"` with a
`pick_voice(slug, override=None) -> str` that rotates across a small allowlist of Kokoro
preset voices (e.g. `af_heart`, `am_adam`, `bf_emma`), deterministic by slug hash so a given
video is stable but the channel isn't monotone. Test: same slug → same voice; different slugs
spread across the allowlist. Records chosen voice in manifest `voice.voice`.

**A2 (Task 3 `yt-media`) — multi-candidate selection + fallback card (fixes CEO F5).**
- `pick_pexels_video`/`pick_pixabay` return the top **N=3** candidates, not one (`per_page: 3`).
  Add `select_candidate(candidates, beat_index) -> dict` choosing by `beat_index % len` so beats
  don't all reuse the same first hit. Test: 3 candidates + 3 beats → 3 distinct picks.
- When **no** candidate is found for a beat, do NOT `result.err`. Instead set the asset to a
  generated fallback card: `make_fallback_card(text, aspect) -> path` (FFmpeg `color` source +
  `drawtext` of `on_screen_text`/narration). Log `source: "fallback"` in manifest. Test: empty
  API response → asset entry with `source=="fallback"` and a real file on disk; run still succeeds.

**A3 (Task 3 `yt-media`) — actually download music (fixes CEO dead-code).** The current
`_fetch` sets `music` but never calls `_download`, and `music.path` is always `None` so the
`sidechaincompress` ducking in Task 5 is dead. Fix: when a Pixabay music hit is found, call
`pick_pixabay(resp, "music")` and `_download(pick["url"], d/"audio"/"music.mp3")`, set
`music.path = "audio/music.mp3"`. If none found, leave `music=None` (stitch already tolerates
it). Test: music hit → `audio/music.mp3` exists and `manifest.stages.music.path` is set.

**A4 (Task 5 `yt-stitch`) — motion variety.** `zoompan_clause` takes a `direction` arg
(`in`/`out`/`pan-l`/`pan-r`) selected by `beat_index % 4` so motion isn't identical every clip.
Test: 4 beats → 4 distinct zoompan expressions.

**A5 (Task 6 smoke test) — hermetic media (fixes design contradiction).** The smoke test must
not require live API keys. Add a `fixtures/media/` with one tiny jpg + mp4 and a
`PIPELINE_MEDIA_FIXTURE=1` env that makes `yt-media` read local fixtures instead of HTTP. Smoke
test sets it; the live path is exercised by a separate `@needs_keys`-gated test.

**A6 (all skills) — drop the `parents[4]` import hack.** Add `tests/conftest.py` and a small
`pipeline` install (`pip install -e .` with a minimal `pyproject.toml`) so scripts import
`pipeline` normally. Removes the brittle relative-depth path insert.

---

### Task 7: `yt-guard` skill — pre-publish Content-ID + license gate (monetization-critical)

**Files:**
- Create: `.claude/skills/yt-guard/SKILL.md`
- Create: `.claude/skills/yt-guard/scripts/preflight_check.py`
- Test: `tests/test_guard.py`

**Interfaces:**
- Consumes: `pipeline.result`, `pipeline.manifest`; reads manifest `media.assets`, `music`.
- Produces:
  - `preflight_check.license_gaps(manifest: dict) -> list[str]` → asset entries missing a `license`.
  - `preflight_check.contentid_checklist(manifest: dict) -> list[dict]` → per-music-track
    `{"title","url","search_query"}` for a manual "track + Content ID" spot-check.
  - `preflight_check.verdict(manifest) -> dict` → `{"publishable": bool, "blockers": [...]}`.
  - CLI: `python preflight_check.py <slug>` → writes manifest stage `guard` with verdict; exits
    non-publishable if any asset lacks a logged license.

- [ ] **Step 1: Failing tests**

`tests/test_guard.py`:
```python
import importlib.util, pathlib
spec = importlib.util.spec_from_file_location(
    "preflight_check",
    pathlib.Path(".claude/skills/yt-guard/scripts/preflight_check.py"))
pf = importlib.util.module_from_spec(spec); spec.loader.exec_module(pf)

def test_license_gaps_flags_missing():
    m = {"stages": {"media": {"assets": [
        {"beat": 1, "license": "Pexels License"},
        {"beat": 2, "license": ""}]}, "music": {"license": "CC0"}}}
    assert pf.license_gaps(m) == ["beat 2"]

def test_verdict_blocks_on_gap():
    m = {"stages": {"media": {"assets": [{"beat": 1, "license": ""}]},
                    "music": {"license": "CC0"}}}
    v = pf.verdict(m)
    assert v["publishable"] is False and v["blockers"]

def test_verdict_passes_clean():
    m = {"stages": {"media": {"assets": [{"beat": 1, "license": "Pexels License"}]},
                    "music": {"license": "CC0", "path": "audio/music.mp3"}}}
    assert pf.verdict(m)["publishable"] is True
```

- [ ] **Step 2: Run to verify fail** — `.venv/bin/pytest tests/test_guard.py -v` → module not found.

- [ ] **Step 3: Implement `preflight_check.py`**

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from pipeline import result, manifest  # noqa: E402


def license_gaps(m):
    gaps = []
    for a in m["stages"].get("media", {}).get("assets", []):
        if not a.get("license"):
            gaps.append(f"beat {a.get('beat')}")
    if m["stages"].get("music", {}).get("path") and not m["stages"]["music"].get("license"):
        gaps.append("music")
    return gaps


def contentid_checklist(m):
    music = m["stages"].get("music", {})
    if not music.get("path"):
        return []
    return [{"title": music.get("title", "music.mp3"),
             "url": music.get("url", ""),
             "search_query": f'{music.get("title", "")} Content ID'}]


def verdict(m):
    blockers = [f"asset missing license: {g}" for g in license_gaps(m)]
    return {"publishable": not blockers, "blockers": blockers,
            "contentid_checklist": contentid_checklist(m)}


def _run(slug):
    m = manifest.load(slug)
    v = verdict(m)
    manifest.set_stage(slug, "guard",
                       status="done" if v["publishable"] else "blocked", **v)
    return result.ok(**v) if v["publishable"] else result.err(
        "not publishable: " + "; ".join(v["blockers"]), **v)


if __name__ == "__main__":
    result.run(lambda: _run(sys.argv[1]))
```

- [ ] **Step 4: Run to verify pass** — `.venv/bin/pytest tests/test_guard.py -v` → PASS.

- [ ] **Step 5: SKILL.md** (`.claude/skills/yt-guard/SKILL.md`):
```markdown
---
name: yt-guard
description: Pre-publish safety gate for a video project — verifies every media/music asset has a logged license and surfaces a Content-ID spot-check checklist before the video is allowed to publish. Use after yt-stitch and before yt-publish.
---

# yt-guard
Reads `manifest.json`, confirms every asset carries a license, and prints a "track + Content ID"
spot-check list. Blocks (non-zero, manifest `guard.status="blocked"`) if any license is missing.
This protects ad revenue: an unverified track silently redirects monetization via Content ID.

## Run
`python .claude/skills/yt-guard/scripts/preflight_check.py <slug>`
```

- [ ] **Step 6: Commit**
```bash
git add .claude/skills/yt-guard/ tests/test_guard.py
git commit -m "feat: yt-guard pre-publish Content-ID + license gate"
```

---

### Task 8: `yt-publish` skill — upload checklist + retention-feedback loop (D2=B)

**Files:**
- Create: `.claude/skills/yt-publish/SKILL.md`
- Create: `.claude/skills/yt-publish/scripts/publish_record.py`
- Test: `tests/test_publish.py`

**Interfaces:**
- Consumes: `pipeline.result`, `pipeline.manifest`.
- Produces:
  - `publish_record.upload_checklist(manifest) -> list[str]` → ordered manual-upload steps
    (title, description with sources, both renders, tags, end screen).
  - `publish_record.record_publish(slug, video_id, notes_path="published.jsonl") -> dict` →
    appends `{slug, video_id, title, published_at_placeholder, outputs}` to a channel-level
    `published.jsonl` for later retention review. (Timestamp filled by caller, not in-script —
    `Date.now` is avoided in pure code; the orchestrator stamps it.)
  - CLI: `python publish_record.py <slug> --video-id <id>` → records the publish row, sets
    manifest stage `publish`.

- [ ] **Step 1: Failing tests**

`tests/test_publish.py`:
```python
import importlib.util, pathlib, json
spec = importlib.util.spec_from_file_location(
    "publish_record",
    pathlib.Path(".claude/skills/yt-publish/scripts/publish_record.py"))
pr = importlib.util.module_from_spec(spec); spec.loader.exec_module(pr)

def test_upload_checklist_mentions_both_renders():
    m = {"slug": "demo", "title": "T",
         "stages": {"stitch": {"outputs": ["out/video_9x16.mp4", "out/video_16x9.mp4"]}}}
    steps = pr.upload_checklist(m)
    joined = " ".join(steps)
    assert "9x16" in joined and "16x9" in joined

def test_record_publish_appends(tmp_path):
    p = tmp_path / "published.jsonl"
    pr.record_publish_row(p, {"slug": "demo", "video_id": "abc", "title": "T"})
    rows = [json.loads(l) for l in p.read_text().splitlines()]
    assert rows[-1]["video_id"] == "abc"
```

- [ ] **Step 2: Run to verify fail** — module not found.

- [ ] **Step 3: Implement `publish_record.py`**

```python
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))
from pipeline import result, manifest  # noqa: E402


def upload_checklist(m):
    outs = m["stages"].get("stitch", {}).get("outputs", [])
    title = m.get("title", "")
    return [
        f"Title: {title}",
        "Description: 2-3 sentence summary + source citations (YPP value signal)",
        f"Upload 16:9 long-form: {next((o for o in outs if '16x9' in o), '?')}",
        f"Upload 9:16 Short: {next((o for o in outs if '9x16' in o), '?')}",
        "Tags: topic keywords; add end screen + a pinned comment",
        "After 48h: record views + average-view-duration into retention notes",
    ]


def record_publish_row(path, row):
    with open(path, "a") as f:
        f.write(json.dumps(row) + "\n")


def _run(slug, video_id):
    m = manifest.load(slug)
    row = {"slug": slug, "video_id": video_id, "title": m.get("title", ""),
           "outputs": m["stages"].get("stitch", {}).get("outputs", [])}
    record_publish_row(Path("published.jsonl"), row)
    manifest.set_stage(slug, "publish", status="done", video_id=video_id)
    return result.ok(checklist=upload_checklist(m), recorded=row)


if __name__ == "__main__":
    vid = sys.argv[sys.argv.index("--video-id") + 1] if "--video-id" in sys.argv else "PENDING"
    result.run(lambda: _run(sys.argv[1], vid))
```

- [ ] **Step 4: Run to verify pass** — PASS.

- [ ] **Step 5: SKILL.md** (`.claude/skills/yt-publish/SKILL.md`):
```markdown
---
name: yt-publish
description: Final stage — prints the manual YouTube upload checklist for a finished video project (both aspect ratios, description with sources, end screen) and records the publish into a channel-level published.jsonl so retention can be reviewed later. Use after yt-guard passes.
---

# yt-publish
No YouTube API needed (upload stays manual to respect account safety). Prints the upload
checklist, then records a row in `published.jsonl` keyed by video id. Run a 48h-later pass to
append views + average-view-duration — this is the feedback loop that tells you which topics
and hooks earn watch-time.

## Run
`python .claude/skills/yt-publish/scripts/publish_record.py <slug> --video-id <id>`
```

- [ ] **Step 6: Commit**
```bash
git add .claude/skills/yt-publish/ tests/test_publish.py
git commit -m "feat: yt-publish upload checklist + retention feedback loop"
```

---

### Monetization engine — full target architecture (8 stages)

Incorporates the ad-revenue playbook (compass review 2). The spine built in this plan is **Stage 5
(assembly)** — the LAST step. The revenue-driving stages wrap around it. Build order is by
leverage, not by pipeline order.

**Stage 0 — Niche/RPM config (`niche.json`, one-time + tunable).** Encodes: niche = AI tools &
productivity; target geo = US/UK/CA/AU; competitor seed channels; banned formats (no bare
slideshow/scrolling-text); affiliate program list (recurring SaaS). Everything downstream reads it.
Add a `niche.json` to the repo now (cheap) so later stages have a config target; list the
future-expansion niches (finance, SaaS reviews, storytelling) commented out.

**Stage 1 — `yt-discover` (HIGHEST leverage, build first of the next plan).** Free YouTube Data
API v3 (10k units/day). Cheap enumeration: `channels.list?part=contentDetails` → uploads playlist
(`UC`→`UU` shortcut, with `channels.list` fallback) → `playlistItems.list` → `videos.list?part=
statistics,contentDetails` (≈2–3 units/channel for 50 videos; **avoid `search.list`, 100 units**).
Cast `viewCount` (string) to int; parse `contentDetails.duration` (ISO-8601) and **filter out
Shorts (≤180s) so they don't corrupt the baseline.** Outlier score = `views ÷ median(last N)`;
surface 3x+ (strong) / 10x+ (breakout); apply **≥10,000-view floor**; normalize recency via
views-per-hour or exclude <72h videos. Output a ranked topic queue + commercial-intent flag.
Reddit (PRAW) as a secondary idea source.

**Stage 2 — `yt-script` (research + original long-form scripting).** Per topic: gather primary
sources, synthesize **original** analysis, produce an 8–20 min script (~1,100–3,000 words @
130–150 wpm) with cited sources. Structure by format (Educational: Hook→Problem→Solution→Proof→CTA;
Listicle: teased cold-open→counted items w/ re-hooks→post-mid-roll payoff). Bake in retention
engineering: concrete-outcome hook in first 5s, open loops, re-hooks per section, **flagged natural
mid-roll breakpoints**, and a chapter list. Inject a consistent **channel voice/POV** from a
brand-voice asset. Emits the same `script.json` the spine consumes (plus chapters + midroll flags).

**Stage 3 — `yt-package` (titles/thumbnails/description).** 3–5 title variants (number+promise,
curiosity-with-specificity, authority, warning), keyword front-loaded, ≤60 visible chars, one A/B
challenger. Thumbnail from a branded 1280×720 template via an AI image model + text overlay
(niche-consistent, per-video-distinct), 2 variants. Auto description: keyword-front-loaded,
affiliate links + FTC disclosure near top, source citations, chapters, tags.

**Stage 4 — `yt-guard` (authenticity / anti-demonetization gate — EXPANDED, channel-wide insurance).**
Beyond v1's license/Content-ID check, add: per-video **script-embedding similarity** vs the
channel's recent N scripts (block if cosine > threshold → catches "template with minor variation");
verify presence of original analysis, ≥X cited sources, channel-POV markers; confirm NOT a bare
slideshow; confirm AI-disclosure flag + voice consistency; **require human sign-off** before
assembly. The July-2025 inauthenticity penalty is channel-wide, so this gate is existential.

**Stage 5 — assembly (THIS PLAN, adapted to long-form-first).** Approved long-form script → Kokoro
(locked consistent voice) → media matched per chapter → WhisperX captions → FFmpeg. Primary output
= 16:9 long-form (8–20 min) with chapter markers + flagged mid-roll points; a secondary pass cuts
3–5 vertical 9:16 Shorts from the highest-retention segments.

**Stage 6 — `yt-publish` (EXPANDED).** Beyond v1's checklist + record: set chapters, set manual
mid-roll slots at script-flagged breakpoints (first at ~40–50%), enable AI-disclosure toggle,
schedule for audience peak, stagger Shorts. (`videos.insert` is now ~100 units since Dec-2025, so
programmatic upload is cheap — but keep upload manual in early days for account safety.)

**Stage 7 — `yt-measure` (feedback loop).** Pull per-video CTR, AVD/retention curve, RPM, traffic
source from YouTube Analytics. Find the 3 biggest retention drops; correlate title/thumbnail/format
with CTR/RPM; feed winners back into Stage 1 (topics) and Stage 2 (script patterns).

**Supplementary revenue (config + description automation, not a stage):** stack recurring SaaS
affiliate links (PartnerStack/Impact) from day one with FTC disclosure — often exceeds ad revenue
in this niche and is available before YPP.

**Build priority for the NEXT plans:** Stage 1 + Stage 2 (discovery + long-form scripting) →
Stage 4 (authenticity gate) → Stage 3 (packaging) → Stage 5 long-form adaptation → Stage 6/7.
This spine (Stage 5 core) is the foundation they all feed.

---

## Eng Review — Corrections (accepted scope, all auto-decided as mechanical fixes)

The independent Eng voice found the architecture sound (pure-core/thin-IO split, result
envelope, manifest contract, single-responsibility skills are the right seams) but caught
multiple **critical correctness bugs concentrated in Task 5 (stitch)**. The first real render
would otherwise produce a video shorter than its audio, blurry stills, possibly unloadable
captions, and **no narration whenever music is present**. All fixes below are folded in.

### Architecture (ASCII)
```
 script.json ─┐
              ▼
        [yt-voice] ── Kokoro ──▶ audio/voiceover.wav  + manifest.voice.beat_timings (hook,beats,outro)
              │
              ▼
        [yt-media] ── Pexels/Pixabay ──▶ media/* (≥3 candidates→select; fallback card) + audio/music.mp3
              │                                    + manifest.media.assets[].license
              ▼
        [yt-captions] ── WhisperX+PySBD ──▶ captions.ass
              │
              ▼
        [yt-stitch] ── pure FFmpeg ──▶ out/video_9x16.mp4, out/video_16x9.mp4
              │
              ▼
        [yt-guard] ── license + Content-ID checklist ──▶ manifest.guard.publishable
              │ (blocks if any asset license missing)
              ▼
        [yt-publish] ── upload checklist ──▶ published.jsonl (retention loop)
 manifest.json = single source of truth across all stages (idempotent per stage)
```

### Test diagram (codepath → coverage)
```
 NEW CODEPATHS                              TEST TYPE      COVERED BY
 plan_beats / concat_timings               unit           test_voice
 voice rotation (pick_voice)               unit           test_voice (A1)
 candidate select + fallback card          unit           test_media (A2)
 music download wiring                     unit/integ     test_media (A3)
 pexels/pixabay parse + backoff + cachekey unit           test_media
 group_words (char-offset, contractions)   unit           test_captions (H4)  ← add contraction/number cases
 to_ass / fmt_ts                           unit           test_captions
 ass path escaping                         integ          test_stitch (C3)    ← assert filter loads
 build_command indices + fps + amix        unit           test_stitch (C1/H1/H3)
 visual-coverage == voice-total            unit           test_stitch (C1)    ← NEW assertion
 license_gaps / verdict                    unit           test_guard
 upload_checklist / record_publish         unit           test_publish
 full spine (hermetic media fixture)       smoke          test_smoke (A5/H5)
```

### Critical/High fixes (corrected Task 5 `build_command` + captions)

**C1 — visual timeline must cover the FULL voiceover (hook+beats+outro), not just body beats.**
Drive the timeline from ALL `beat_timings`. Hook (id 0) and outro (id -1) have no `b_roll_keywords`,
so they get a fallback title card sized to their narration duration. Result: `sum(clip_durs) ==
voice_total`, and `-shortest` becomes harmless. Add a test asserting that equality.

**C2 — `zoompan` must render at target dims, not 1280×720.** Set `s={w}x{h}` per aspect and drop
the redundant `-loop 1 -t` (zoompan's `d=` already fixes frame count). No more 720→1920 upscale blur.

**C3 — escape the `ass=` filter path.** Use `ass=filename='captions.ass'` with `\:`,`\\`,`\'`
escaping; add an integration assertion that captions actually load (not just a substring grep).

**H1 — mix voice + ducked music (current chain drops the voice).** Correct audio graph:
```
[Vidx:a]asplit=2[vkey][vmix];
[Midx:a]volume=0.3[bg];
[bg][vkey]sidechaincompress=threshold=0.03:ratio=6:attack=5:release=300[duck];
[duck][vmix]amix=inputs=2:duration=longest:dropout_transition=0[aout]
```
When `music is None`, map `[Vidx:a]` directly (no amix). Add a probe test asserting the mixed
output contains the voice.

**H3 — normalize every segment before concat.** Append `,fps=30,format=yuv420p,setsar=1` to BOTH
the still branch and the video branch so `concat` gets matching fps/SAR/timebase. Force each video
clip to exactly its `dur` (`tpad=stop_mode=clone:stop_duration=...` for short clips).

**H4 — `group_words` desyncs on punctuation/contractions.** Don't reconstruct sentences by
re-splitting on word count. Instead keep WhisperX's per-word list and assign words to PySBD
sentences by **character offset** (accumulate `len(word)+1`), so contractions/numbers/punctuation
don't shift the index. Add tests with `"it's"`, `"3.5"`, and a comma.

**H5 — smoke test: implement A5 hermetic fixture + remove the redundant `mkdir` lines.** The shown
Task 6 test code has three redundant `proj.mkdir` calls and still needs live keys; replace with the
`PIPELINE_MEDIA_FIXTURE=1` local-fixture path so the fast suite runs offline.

### Medium fixes (auto-decided)
- **M1** asset extension from API response media type, not URL string matching.
- **M2** stream `_download` to disk via `iter_content` with a max-bytes cap (avoid OOM on UHD clips).
- **M3** fallback-card `drawtext` uses `textfile=` (or rigorous `:`,`\`,`%`,`'` escaping); test with `it's a "test": 50%`.
- **M4** include `exc.stderr.decode()` in the stitch error envelope so render failures are debuggable.
- **M5** parse args with `argparse` (`slug` positional + `--force` flag) instead of `"--force" in sys.argv`.
- **M6** soften `yt-guard` SKILL.md wording: it's a license gate + Content-ID *checklist*, not an automated fingerprint check (v1 scope).
- **M7 (Task 1)** ADD `pyproject.toml` so A6's `pip install -e .` works and the `parents[4]` hack is removed.

### Task 1 amendment — add `pyproject.toml`
Create `pyproject.toml` in Task 1:
```toml
[project]
name = "yt-pipeline"
version = "0.1.0"
requires-python = ">=3.12"

[tool.setuptools.packages.find]
include = ["pipeline*"]
```
Then `.venv/bin/pip install -e .` in Task 1 Step 1; drop the `sys.path.insert(... parents[4])`
line from every script and `import pipeline` normally. Add `tests/conftest.py` (empty is fine).

### Eng caveats to verify at implementation time (not blockers)
- **Pixabay music endpoint** (N2): the public API may not expose direct mp3 download. Verify before
  relying on music; if absent, `music=None` and ducking is simply inactive (stitch tolerates it).
- **WhisperX `base` int8** is fine for text; word *timing* comes from the wav2vec2 `align` step, so
  model size barely affects timing — but validate caption drift on real TTS audio early.

---

## DX Review — Corrections (accepted scope, all auto-decided)

DX scored **4.5/10** initially — a strong machine-facing contract (envelope, manifest,
idempotency, uniform `<slug> [--force]` CLI, well-triggered SKILL descriptions) on top of a
near-absent human onboarding surface. TTHW ~30–50 min (≈1GB of uncounted model downloads +
torch). Target after fixes: **~7.5/10, TTHW ≤15 min of hands-on steps.** All fixes folded in.

### Developer journey (9-stage) + TTHW
```
 STAGE              BEFORE                         AFTER FIX
 1 discover repo    no README                      README "start here"        (F1)
 2 install deps     6 manual cmds                  scripts/setup.sh one-shot  (F1)
 3 system deps      sudo apt only, uncaught        per-distro doc + preflight  (F4,F8)
 4 get API keys     scattered, no links            README w/ signup links     (F1)
 5 warm models      silent ~1GB first-run pull     scripts/warmup.py + sizes  (F3)
 6 author script    fixture provided               documented                  ok
 7 run pipeline     4-6 manual cmds                make.py one command         (F2)
 8 failures         cryptic tracebacks             problem+cause+fix preflight (F4)
 9 publish          manual                         yt-publish checklist        ok
 TTHW: ~14 steps/30-50min  →  ~6 hands-on steps + one warmup wait
```

### New Task 0: setup, README, warmup, contract doc (do FIRST)
**Files:** `README.md`, `scripts/setup.sh`, `scripts/warmup.py`, `.claude/skills/CONTRACT.md`
- **README.md (F1):** prereq checklist (Python 3.12, ffmpeg, espeak-ng), API signup links
  (https://www.pexels.com/api/, https://pixabay.com/api/docs/), model download sizes
  (Kokoro ~330MB, WhisperX base ~150MB, wav2vec2 align ~360MB) + one-time warmup, the
  venv+install sequence, a copy-paste "first video" block, and `make.py` usage.
- **scripts/setup.sh (F1,F8):** create venv, `pip install -e .` + deps, detect package manager
  (`apt`/`dnf`/`pacman`) for espeak-ng or print the problem+cause+fix message if absent.
- **scripts/warmup.py (F3):** pre-download Kokoro + WhisperX + align models with progress so the
  first real render is fast and offline-capable.
- **.claude/skills/CONTRACT.md (F5):** documents the envelope shape `{success,error,...}`, the
  manifest path + per-stage status lifecycle, env vars, and the canonical stage order — so the
  orchestrator (Claude) learns the cross-stage contract without reading every script.

### New Task 9: `make.py` single-command orchestrator (F2)
**Files:** `make.py` (or `pipeline/run.py`), `tests/test_make.py`
A thin CLI that validates `script.json`, then runs voice → media → captions → stitch → guard →
publish as subprocesses, parsing each JSON envelope and stopping on first `success:false`.
Flags: `--yes` (skip approval gate, default off — the gate prints hook+beats and waits),
`--force-all`, `--aspect {9x16,16x9,both}`, `--voice NAME`, `--music PATH|none`. This collapses
TTHW step 7 from 6 commands to one and serves both the human and Claude. `yt-make` SKILL.md
points at it. Test: pure `plan_stage_order()` + envelope-parsing helper unit-tested; full run
covered by the smoke test.

### Task 1 amendment: `pipeline.preflight` (F4)
Add `pipeline/preflight.py` with `check_binary(name, fix)`, `check_artifact(path, fix)`,
`check_env(var, fix)` — each returns a problem+cause+fix string. Each stage calls the relevant
checks first and returns them via the envelope, e.g.
`"espeak-ng not found — Kokoro needs it. Fix: sudo apt-get install -y espeak-ng (Fedora: dnf install espeak-ng)"`.
Add a `run_ffmpeg(cmd, cwd)` wrapper that always folds `stderr` into the error envelope (M4, all
subprocess calls, not just stitch). Tests: each checker returns the fix text when the thing is absent.

### Override flags (F7) — wire into argparse (M5)
`yt-voice --voice NAME`, `yt-stitch --aspect {9x16,16x9,both}` (default both),
`yt-media --music PATH|none`. Document `PIPELINE_MEDIA_FIXTURE=1` in the README as offline/demo mode.

### F9 — commit `fixtures/media/` (tiny jpg + mp4) and confirm `.gitignore` (`fixtures/cache/` only) doesn't sweep it.

### DX Scorecard
```
 1 Getting started (TTHW)     2 → 8   README + setup.sh + make.py
 2 API/CLI naming guessable   8 → 9   uniform <slug> [--force]; flags added
 3 Error messages actionable  3 → 8   preflight problem+cause+fix + ffmpeg stderr
 4 Docs findable/complete     1 → 8   README + CONTRACT.md
 5 Upgrade/escape hatches     4 → 8   --voice/--aspect/--music/fixture mode
 6 Onboarding portability     3 → 7   per-distro espeak-ng + preflight
 7 Orchestrator ergonomics    7 → 9   CONTRACT.md makes envelope/manifest discoverable
 8 Single-command run         2 → 9   make.py
 OVERALL                    4.5 → ~8
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

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|----------------|-----------|-----------|
| 1 | CEO | Objective = AD REVENUE; add monetization scope | **User decision** (premise gate) | — | User chose C over recommended "learning" |
| 2 | CEO | Add publish+measure loop to v1 (yt-publish) | **User decision** (D2=B) | — | User wants learning signal on hooks/topics |
| 3 | CEO | Voice rotation + multi-candidate media + motion variety | Auto (mechanical) | P1,P2 | Differentiation is the anti-demonetization lever |
| 4 | CEO | Media never hard-fails → fallback card (F5) | Auto (mechanical) | P1 | One missing clip must not kill a render |
| 5 | CEO | Fix dead music download code | Auto (mechanical) | P5 | Ducking referenced but never wired |
| 6 | CEO | Add yt-guard pre-publish license/Content-ID gate | Auto + user-intent | P1 | Protects ad revenue from silent claims |
| 7 | CEO | Differentiation backlog items → TODOS | Auto | P3 | Out of v1 spine blast radius |
| 8 | Eng | C1 visual coverage == voice total | Taste (approach) | P5 | Hook/outro get title cards (vs stretch beats) |
| 9 | Eng | C2 zoompan target dims (no 720p blur) | Auto (mechanical) | P5 | Clear correctness/quality fix |
| 10 | Eng | C3 escape ass= filter path | Auto (mechanical) | P5 | Render breaks on real paths |
| 11 | Eng | H1 amix voice+ducked music | Auto (mechanical) | P1 | Current graph drops narration |
| 12 | Eng | H3 fps/sar/format normalize before concat | Auto (mechanical) | P5 | Mixed-fps stock breaks concat |
| 13 | Eng | H4 char-offset caption alignment | Auto (mechanical) | P1 | Word-count resplit desyncs on punctuation |
| 14 | Eng | H5 hermetic smoke fixture + mkdir cleanup | Auto (mechanical) | P1 | Only e2e guard was non-functional |
| 15 | Eng | M1-M7 (ext detect, streaming dl, drawtext escape, ffmpeg stderr, argparse, guard wording, pyproject) | Auto (mechanical) | P5 | Clear-win robustness fixes |
| 16 | DX | Add README + setup.sh + warmup.py + CONTRACT.md (Task 0) | Auto (mechanical) | P1 | Onboarding surface absent |
| 17 | DX | Add make.py single-command orchestrator (Task 9) | Auto (mechanical) | P5 | 6 manual cmds → 1; serves human + Claude |
| 18 | DX | pipeline.preflight problem+cause+fix + run_ffmpeg | Auto (mechanical) | P1 | Errors were cryptic tracebacks |
| 19 | DX | Override flags --voice/--aspect/--music + fixture mode | Auto (mechanical) | P5 | Cheap escape hatches via argparse |

## GSTACK REVIEW REPORT

| Review | Trigger | Why | Runs | Status | Findings |
|--------|---------|-----|------|--------|----------|
| CEO Review | `/plan-ceo-review` | Scope & strategy | 1 | issues_open | objective set to AD REVENUE; +6 monetization scope items; 4 strategic criticals surfaced |
| Codex Review | `/codex review` | Independent 2nd opinion | 0 | — | Codex CLI not installed |
| Eng Review | `/plan-eng-review` | Architecture & tests (required) | 1 | issues_open | arch sound; 3 critical + 5 high + 7 medium bugs (stitch/media) all auto-fixed |
| Design Review | `/plan-design-review` | UI/UX gaps | 0 | skipped | no UI scope (CLI/skills pipeline) |
| DX Review | `/plan-devex-review` | Developer experience gaps | 1 | issues_open | 4.5→~8/10; +Task 0 (README/setup/warmup/contract), +Task 9 (make.py), preflight |

- **VOICES:** Codex unavailable (not installed) → all phases ran `[subagent-only]` (independent Claude subagent per phase). CEO 1/6 confirmed, Eng 2/6 confirmed, DX scorecard produced. Single-voice critical findings flagged regardless.
- **PLAYBOOK INCORPORATED:** compass review 2 (ad-revenue playbook) folded in — niche locked to **AI tools & productivity**, **long-form-first** output strategy, and the full 8-stage monetization engine roadmap (discovery → scripting → authenticity gate → packaging → assembly → publish/mid-roll → feedback). Future niches noted: finance, SaaS reviews, storytelling.
- **VERDICT:** CEO + ENG + DX reviewed; plan amended with all auto-decided fixes + monetization playbook. Ready to implement.

**UNRESOLVED DECISIONS:**
- C1 (Eng): hook/outro visual coverage — defaulting to **title cards** (recommended); change at build time if you prefer stretching adjacent beat clips.

