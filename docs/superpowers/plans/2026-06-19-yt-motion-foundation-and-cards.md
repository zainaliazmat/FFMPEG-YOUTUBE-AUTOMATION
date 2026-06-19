# yt-motion (Foundation + Cards) Implementation Plan — v2.1

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional `yt-motion` stage that renders brand-locked animated **cards** (HyperFrames → MP4) into the existing FFmpeg `yt-stitch` path, behind a human Gate 4 — as an **outro card swap** and **chapter-card short-inserts**, with all orchestration unit-tested without Docker.

**Architecture:** Cards are **timeline segments, not beat overrides** (corrected from v1). A motion card either *replaces the outro card segment* (`id -1`) or is *inserted as a short head-flash on a chapter's first beat* (mirroring the existing logo-reveal insert in `stitch_video.py:279-289`). The HyperFrames/Docker render is an **injected dependency** (`render_fn`), so the gate, fit, cache, retries, fallback, manifest write and stitch-invalidation are pure Python and fully unit-tested; only the real HTML→MP4 invocation needs Docker. The brand system is **hand-authored + committed**, merely *injected* per project.

**Tech Stack:** Python 3.12, pytest (`tmp_path` + `monkeypatch.chdir`), FFmpeg 6.1.1, Node 22 + headless Chrome + Docker (HyperFrames, render path only), the existing `pipeline.{manifest,assets,result,schema}` modules.

## Global Constraints

- **Engine:** HyperFrames via **Docker mode, pinned image tag**, persisted to `manifest.motion.engine_version` (the *resolved image digest*, not the literal name).
- **Cards are segments, not beat overrides.** `kind:beat` (content override) and `kind:overlay` are **out of scope** here (Phases 3/2); their merge helpers are not built in this plan (nothing consumes them yet).
- **Hook (`id 0`) stays static `drawtext`.** Only the **outro (`id -1`)** and **chapter** cards animate.
- **Outro card** fills the outro segment duration (from `beat_timings`); **chapter card** is a fixed short flash (`MOTION_CARD_SEC`, default 3.0s) that eats the front of the chapter's first beat, footage fills the rest.
- **One shared video spec** (`pipeline/video_spec.py`) governs both the renderer and stitch: `1920×1080`, `30` fps, `yuv420p`, `bt709`, `tv` range. Color/range are tagged explicitly on the motion encode.
- **All comps render muted but carry a silent audio track** (so concat against narrated segments doesn't break).
- **Brand system hand-authored + committed**; `brand.py` only injects it. `DejaVu Sans` must be bundled in the pinned image and `document.fonts.ready` must resolve before capture.
- **`confirmed: false` is NEVER rendered** (hard gate, strict `is True`). The schema validates `confirmed` is a real `bool`.
- **Every stage script returns a `result` envelope and never raises** (`pipeline/result.py`).
- **Idempotent:** skip when `manifest.stage_done(slug,"motion")` unless `--force`; `--init` never marks done. A normal run skips an **unchanged** comp (content hash); `--force` re-renders every targeted comp.
- **Typed errors:** every failure is a `MotionError(code, message)` with an `ERR_*` code + `next_action` hint.
- **Render is flaky:** wrap `render_fn` in retries (2) + a per-comp wall-clock timeout; only fall back to b-roll after retries are exhausted.
- **CI cannot run Docker/Chrome.** Render-path tests inject a fake `render_fn`; real-engine checks are manual/`@needs_docker` and clearly marked.

---

## File Structure

**New files**
- `pipeline/video_spec.py` — shared canonical resolution/fps/pixfmt/color constants.
- `.claude/skills/yt-motion/SKILL.md` — operator guide (init→review→confirm→render→re-stitch).
- `.claude/skills/yt-motion/scripts/motion_render.py` — the stage script.
- `.claude/skills/yt-motion/scripts/brand.py` — injects the committed brand system.
- `.claude/skills/yt-motion/templates/tokens.css`, `brand.md` — hand-authored, committed.
- `.claude/skills/yt-motion/templates/card/chapter.html`, `outro.html` — comp templates.
- `pipeline/motion_fit.py` — pure timing-fit (floor + ceiling).
- `tests/test_video_spec.py`, `test_motion_fit.py`, `test_motion_render.py`, `test_brand.py`, plus additions to `test_schema.py`, `test_manifest.py`, `test_stitch.py`.

**Modified files**
- `pipeline/manifest.py:11` — add `"motion"` to `STAGES`.
- `pipeline/schema.py` — add `validate_motion`.
- `.claude/skills/yt-stitch/scripts/stitch_video.py` — consume motion card assets in `plan_segments` (outro swap + chapter insert).
- `tests/conftest.py` — put the yt-motion `scripts/` dir on `sys.path` for tests.

**Deferred to later plans (not built here):** `pipeline/lottie_gen.py` productionization, `assets.overlay_layers()` / `assets.apply_motion_overrides()`, the alpha-overlay compositor (all Phase 2/3 — they have no Phase-1 consumer).

---

## Task 1: Shared video spec

**Files:**
- Create: `pipeline/video_spec.py`
- Test: `tests/test_video_spec.py`

**Interfaces:**
- Produces: module constants `WIDTH=1920, HEIGHT=1080, FPS=30, PIXFMT="yuv420p", COLOR="bt709", RANGE="tv"` and `size_str() -> "1920x1080"`. Imported by both `motion_render._docker_render` and `stitch_video.py`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_video_spec.py`:

```python
from pipeline import video_spec as vs


def test_canonical_spec_values():
    assert (vs.WIDTH, vs.HEIGHT, vs.FPS) == (1920, 1080, 30)
    assert vs.PIXFMT == "yuv420p"
    assert vs.COLOR == "bt709" and vs.RANGE == "tv"
    assert vs.size_str() == "1920x1080"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_video_spec.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.video_spec'`.

- [ ] **Step 3: Write the implementation**

Create `pipeline/video_spec.py`:

```python
"""Canonical output spec shared by the motion renderer and yt-stitch. Both must
agree on size/fps/pixel-format/color or concatenated motion segments judder or
shift color against FFmpeg footage."""
WIDTH = 1920
HEIGHT = 1080
FPS = 30
PIXFMT = "yuv420p"
COLOR = "bt709"   # matrix/primaries/transfer for the motion encode
RANGE = "tv"      # limited range, matches typical FFmpeg footage


def size_str():
    return f"{WIDTH}x{HEIGHT}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_video_spec.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/video_spec.py tests/test_video_spec.py
git commit -m "feat(motion): shared canonical video_spec (size/fps/pixfmt/color)"
```

---

## Task 2: Register the `motion` manifest stage

**Files:**
- Modify: `pipeline/manifest.py:11`
- Test: `tests/test_manifest.py`

**Interfaces:**
- Produces: `"motion"` is seeded by `init()` as `pending`.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_manifest.py`:

```python
def test_motion_is_a_known_stage(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = manifest.init("demo")
    assert m["stages"]["motion"]["status"] == "pending"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_manifest.py::test_motion_is_a_known_stage -v`
Expected: FAIL with `KeyError: 'motion'`.

- [ ] **Step 3: Add the stage**

In `pipeline/manifest.py:11` change:

```python
STAGES = ("capture", "voice", "media", "captions", "stitch")
```

to:

```python
STAGES = ("capture", "voice", "media", "motion", "captions", "stitch")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_manifest.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/manifest.py tests/test_manifest.py
git commit -m "feat(motion): register motion as a known manifest stage"
```

---

## Task 3: Committed brand tokens + `brand.py` injection

**Files:**
- Create: `.claude/skills/yt-motion/templates/tokens.css`, `.claude/skills/yt-motion/templates/brand.md`
- Create: `.claude/skills/yt-motion/scripts/brand.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_brand.py`

**Interfaces:**
- Produces: `brand.generate(slug, root="project") -> {"tokens": "<path>", "frame": "<path>"}`; copies the committed templates verbatim (deterministic, idempotent). No `channel.json` derivation.

**Human step (do once, before Task 11 render):** approve the committed `tokens.css`/`brand.md` as a static swatch sheet. Values below are an on-brand start anchored on the existing `#0b1a2a`; refine palette/type by hand, keep the banned-motion list + duration scale.

- [ ] **Step 1: Write the committed templates**

Create `.claude/skills/yt-motion/templates/tokens.css`:

```css
/* The Leverage Loop — committed motion design tokens. Hand-authored, not generated.
   "motion confirms, it doesn't sell." */
:root {
  --bg: #0b1a2a;          /* existing CARD_BG */
  --accent: #38bdf8;
  --verdict: #f5b700;     /* the one "verdict" semantic color */
  --ink: #ffffff;
  --muted: #93a4b3;
  --grid: 8px;
  --font-head: "DejaVu Sans", system-ui, sans-serif;  /* must be bundled in the image */
  --ease: cubic-bezier(0.22, 1, 0.36, 1);             /* the ONLY easing family */
  --dur-in: 500ms;
  --dur-emph: 250ms;
  --dur-out: 300ms;
  /* BANNED: bounce, elastic, overshoot, springs, neon, >1 concurrent motion,
     motion faster than 200ms or slower than 800ms. */
}
```

Create `.claude/skills/yt-motion/templates/brand.md`:

```markdown
# The Leverage Loop — motion frame.md (committed)

Palette: bg #0b1a2a, accent #38bdf8, verdict #f5b700, ink #fff, muted #93a4b3.
Type: DejaVu Sans Bold, centered. Grid: 8px.
Motion: one ease-out family cubic-bezier(0.22,1,0.36,1). Entrances 400-600ms,
emphasis 250ms, exits 300ms. One primary element at a time; supporting settles first.
Grammar: fade + 24px rise in, fade out. BANNED: bounce/elastic/overshoot/springs/neon/
>1 concurrent motion / <200ms / >800ms.
Statement: motion confirms, it doesn't sell. Built for the camera — no web chrome.
```

- [ ] **Step 2: Wire the test import path**

Replace `tests/conftest.py` contents with:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent
                       / ".claude" / "skills" / "yt-motion" / "scripts"))
```

- [ ] **Step 3: Write the failing test**

Create `tests/test_brand.py`:

```python
from pathlib import Path
import brand


def test_generate_copies_committed_tokens_deterministically(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pipeline import manifest
    manifest.project_dir("demo")
    out1 = brand.generate("demo")
    tokens = Path(out1["tokens"]).read_text()
    frame = Path(out1["frame"]).read_text()
    assert "--ease: cubic-bezier(0.22, 1, 0.36, 1)" in tokens
    assert "motion confirms, it doesn't sell" in frame
    out2 = brand.generate("demo")
    assert Path(out2["tokens"]).read_text() == tokens
    assert Path(out2["frame"]).read_text() == frame
```

- [ ] **Step 4: Run test to verify it fails**

Run: `pytest tests/test_brand.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'brand'`.

- [ ] **Step 5: Write the implementation**

Create `.claude/skills/yt-motion/scripts/brand.py`:

```python
"""Inject the COMMITTED brand system into a project. Deterministic: copies the
hand-authored templates verbatim. It never derives design from channel.json."""
import sys
import shutil
from pathlib import Path

# Make `pipeline` importable when run as a script (mirrors capture_sites.py:38).
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pipeline import manifest  # noqa: E402

_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def generate(slug, root="project"):
    d = manifest.project_dir(slug, root) / "motion"
    d.mkdir(parents=True, exist_ok=True)
    tokens, frame = d / "tokens.css", d / "brand.md"
    shutil.copyfile(_TEMPLATES / "tokens.css", tokens)
    shutil.copyfile(_TEMPLATES / "brand.md", frame)
    return {"tokens": str(tokens), "frame": str(frame)}
```

- [ ] **Step 6: Run test to verify it passes, then commit**

Run: `pytest tests/test_brand.py -v`
Expected: PASS.

```bash
git add .claude/skills/yt-motion/templates/ .claude/skills/yt-motion/scripts/brand.py tests/test_brand.py tests/conftest.py
git commit -m "feat(motion): committed brand tokens + deterministic brand.py injection"
```

---

## Task 4: `motion.json` schema validation (cards)

**Files:**
- Modify: `pipeline/schema.py`
- Test: `tests/test_schema.py`

**Interfaces:**
- Produces: `schema.validate_motion(motion, valid_card_beats) -> list[str]` (empty = valid). `motion` None/absent → valid. `valid_card_beats` is whatever placeable-position set the caller passes (here: chapter `start_beat`s ∪ `{-1}`). Each item: `beat` in `valid_card_beats`, `kind` in `{"card","overlay","beat"}`, `template` non-empty str, **`confirmed` a real `bool`** (strings/ints rejected so the hard gate can't be fooled).

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_schema.py`:

```python
from pipeline import schema


def test_validate_motion_absent_is_valid():
    assert schema.validate_motion(None, {-1, 0, 8}) == []


def test_validate_motion_good_card_items():
    m = [
        {"beat": -1, "kind": "card", "template": "card/outro", "confirmed": False},
        {"beat": 8, "kind": "card", "template": "card/chapter", "confirmed": True},
    ]
    assert schema.validate_motion(m, {-1, 0, 8}) == []


def test_validate_motion_rejects_nonbool_confirmed():
    m = [{"beat": 8, "kind": "card", "template": "card/chapter", "confirmed": "true"}]
    errs = schema.validate_motion(m, {8})
    assert any("confirmed must be a boolean" in e for e in errs)


def test_validate_motion_rejects_bad_kind_beat_and_template():
    m = [{"beat": 99, "kind": "explode", "template": "", "confirmed": False}]
    errs = schema.validate_motion(m, {8})
    assert any("kind" in e for e in errs)
    assert any("beat 99" in e for e in errs)
    assert any("template" in e for e in errs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_schema.py -k validate_motion -v`
Expected: FAIL with `AttributeError: module 'pipeline.schema' has no attribute 'validate_motion'`.

- [ ] **Step 3: Write the implementation**

Append to `pipeline/schema.py`:

```python
_MOTION_KINDS = ("card", "overlay", "beat")


def validate_motion(motion, valid_card_beats):
    """Validate a motion.json plan (yt-motion input). None/absent -> valid.
    valid_card_beats is the set of placeable ids the caller allows (chapter
    start_beats plus {-1}). confirmed MUST be a real bool so the strict is-True
    render gate can't be fooled by 'true'/1."""
    if motion is None:
        return []
    errs = []
    if not isinstance(motion, list):
        return ["motion must be an array"]
    valid = set(valid_card_beats)
    for i, item in enumerate(motion):
        if not isinstance(item, dict):
            errs.append(f"motion[{i}] must be an object")
            continue
        b = item.get("beat")
        if not (isinstance(b, int) and not isinstance(b, bool)) or b not in valid:
            errs.append(f"motion[{i}] beat {b!r} is not a placeable card position")
        if item.get("kind") not in _MOTION_KINDS:
            errs.append(f"motion[{i}] kind must be one of {_MOTION_KINDS}")
        if not item.get("template") or not isinstance(item.get("template"), str):
            errs.append(f"motion[{i}] missing non-empty string template")
        if not isinstance(item.get("confirmed"), bool):
            errs.append(f"motion[{i}] confirmed must be a boolean")
    return errs
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/schema.py tests/test_schema.py
git commit -m "feat(motion): validate_motion (card positions, kinds, bool confirmed)"
```

---

## Task 5: Timing-fit calculator (floor + ceiling)

**Files:**
- Create: `pipeline/motion_fit.py`
- Test: `tests/test_motion_fit.py`

**Interfaces:**
- Produces:
  - `motion_fit.outro_hold(comp_min_s, outro_s, max_card_s) -> (hold, warn)`: hold = `outro_s - comp_min_s` (≥0), **never clamped** — an end card may legitimately run 15-20s. `warn=True` flags a suspiciously long outro (`outro_s > max_card_s`) for the operator, but the card still fills the full window so the rendered MP4 length always equals the outro segment (no freeze/desync).
  - `motion_fit.chapter_fits(beat_s, card_s, min_footage_s) -> bool`: a chapter card flash fits only if the beat is long enough to host the flash *and* leave footage (`beat_s >= card_s + min_footage_s`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_motion_fit.py`:

```python
from pipeline import motion_fit


def test_outro_hold_fills_full_window_within_threshold():
    # comp min 2.0, outro 7.0 -> hold 5.0 (fills the whole 7s), no warn
    assert motion_fit.outro_hold(2.0, 7.0, 8.0) == (5.0, False)


def test_outro_hold_long_outro_warns_but_does_not_clamp():
    # outro 40s -> hold 38.0 (still fills the full window), warn=True
    assert motion_fit.outro_hold(2.0, 40.0, 8.0) == (38.0, True)


def test_chapter_fits_only_with_room_for_flash_plus_footage():
    assert motion_fit.chapter_fits(11.0, 3.0, 2.0) is True    # 11 >= 3 + 2
    assert motion_fit.chapter_fits(4.0, 3.0, 2.0) is False    # 4 < 3 + 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_motion_fit.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'pipeline.motion_fit'`.

- [ ] **Step 3: Write the implementation**

Create `pipeline/motion_fit.py`:

```python
"""Timing-fit for motion cards.

Outro card fills the outro segment via an elastic HOLD (never stretching the
intro/outro animation), capped so a mis-tagged runaway outro warns instead of
freezing for 40s. Chapter card is a fixed short flash that must leave footage
behind it on the chapter's first beat."""


def outro_hold(comp_min_s, outro_s, max_card_s):
    """Return (hold_seconds, warn). hold = outro_s - comp_min_s, NEVER clamped:
    the outro card IS the outro, so it always fills the full window (rendered
    length == outro segment length -> no freeze/desync). warn flags a long outro
    so the operator can sanity-check, but the card still fills it."""
    return round(max(outro_s - comp_min_s, 0.0), 3), outro_s > max_card_s


def chapter_fits(beat_s, card_s, min_footage_s):
    """A chapter flash fits only if the beat can host the flash and still show
    footage afterward."""
    return beat_s >= card_s + min_footage_s
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_motion_fit.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add pipeline/motion_fit.py tests/test_motion_fit.py
git commit -m "feat(motion): timing-fit (outro elastic hold w/ ceiling, chapter fit guard)"
```

---

## Task 6: `doctor()` preflight + content-aware `comp_key` + typed errors

**Files:**
- Create: `.claude/skills/yt-motion/scripts/motion_render.py`
- Test: `tests/test_motion_render.py`

**Interfaces:**
- Produces:
  - `MotionError(Exception)` with `.code`; constants `ERR_NO_PLAN, ERR_UNCONFIRMED, ERR_MISSING_DOCKER, ERR_MISSING_NODE, ERR_MISSING_HF, ERR_NO_TIMINGS, ERR_UNFITTABLE, ERR_RENDER_FAILED, ERR_INVALID_PLAN`.
  - `doctor(which=shutil.which) -> dict`: `{"ok": bool, "missing": [...], "next_action": str}`.
  - `comp_key(item, duration, template_bytes, tokens_bytes, engine_version) -> str`: sha256 over `template name + data + lottie + rounded duration + template_bytes + tokens_bytes + engine_version`. **Editing the HTML/tokens OR bumping the engine changes the key** — so an engine bump busts the per-item cache (normal runs re-render) and flips the `changed` set (stitch invalidates). `template_bytes`/`tokens_bytes` are injected so the function stays pure/testable.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_motion_render.py`:

```python
import motion_render as mr


def test_doctor_flags_missing_docker_with_next_action():
    def which(tool):
        return None if tool == "docker" else f"/usr/bin/{tool}"
    r = mr.doctor(which=which)
    assert r["ok"] is False and "docker" in r["missing"]
    assert "skip motion" in r["next_action"].lower()


def test_doctor_ok_when_all_present():
    r = mr.doctor(which=lambda t: f"/usr/bin/{t}")
    assert r["ok"] is True and r["missing"] == []


def test_comp_key_changes_with_template_tokens_duration_and_engine():
    item = {"template": "card/chapter", "data": {"title": "X"}, "lottie": None}
    html, tok, eng = b"<html>v1</html>", b":root{--bg:#0b1a2a}", "hf@sha256:aaa"
    base = mr.comp_key(item, 3.0, html, tok, eng)
    assert base == mr.comp_key(item, 3.0, html, tok, eng)
    assert base != mr.comp_key(item, 3.0, b"<html>v2</html>", tok, eng)   # html edit
    assert base != mr.comp_key(item, 5.0, html, tok, eng)                 # duration
    assert base != mr.comp_key(item, 3.0, html, b":root{--bg:#000}", eng) # tokens edit
    assert base != mr.comp_key(item, 3.0, html, tok, "hf@sha256:bbb")     # engine bump
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_motion_render.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'motion_render'`.

- [ ] **Step 3: Write the implementation**

Create `.claude/skills/yt-motion/scripts/motion_render.py`:

```python
"""yt-motion: render brand-locked motion CARDS into the FFmpeg pipeline.

  motion_render.py <slug> --init     # scaffold motion.json (confirmed:false)
  motion_render.py <slug> [--force] [--only <beat>]
  motion_render.py <slug> --doctor

Cards are timeline SEGMENTS, not beat overrides: the outro card (beat -1) swaps
the drawtext outro; a chapter card (beat = chapter start_beat) is a short flash
inserted at the front of that beat. The HyperFrames render is injected (render_fn)
so the gate/fit/cache/retry/fallback are unit-tested without Docker."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # make `pipeline` importable

ERR_NO_PLAN = "motion_no_plan"
ERR_INVALID_PLAN = "motion_invalid_plan"
ERR_UNCONFIRMED = "motion_unconfirmed"
ERR_NO_TIMINGS = "motion_no_timings"
ERR_MISSING_DOCKER = "motion_missing_docker"
ERR_MISSING_NODE = "motion_missing_node"
ERR_MISSING_HF = "motion_missing_hf"
ERR_UNFITTABLE = "motion_unfittable"
ERR_RENDER_FAILED = "motion_render_failed"

_INSTALL = {
    "docker": "install Docker Engine then `sudo systemctl enable --now docker`",
    "node": "install Node 22+ resolvable in non-interactive shells",
    "hyperframes": "install the HyperFrames CLI (`npm i -g hyperframes`)",
}


class MotionError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def doctor(which=shutil.which):
    missing = [t for t in ("docker", "node", "hyperframes") if which(t) is None]
    if not missing:
        return {"ok": True, "missing": [], "next_action": ""}
    fixes = "; ".join(_INSTALL[t] for t in missing)
    return {"ok": False, "missing": missing,
            "next_action": f"{fixes}. Or skip motion and keep stock b-roll "
                           f"(motion is optional)."}


def comp_key(item, duration, template_bytes, tokens_bytes, engine_version):
    """Cache key over the RESOLVED composition: template name+content, data,
    lottie, duration, brand tokens, AND engine_version. Editing the HTML/tokens
    or bumping the pinned engine re-renders (and flips the stitch-change diff)."""
    h = hashlib.sha256()
    h.update(json.dumps({
        "template": item.get("template"),
        "data": item.get("data"),
        "lottie": item.get("lottie"),
        "duration": round(float(duration), 3),
        "engine": engine_version,
    }, sort_keys=True).encode())
    h.update(template_bytes or b"")
    h.update(tokens_bytes or b"")
    return h.hexdigest()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_motion_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/yt-motion/scripts/motion_render.py tests/test_motion_render.py
git commit -m "feat(motion): doctor preflight, typed errors, content-aware comp_key"
```

---

## Task 7: `--init` scaffold (chapters + outro) and plan validation

**Files:**
- Modify: `.claude/skills/yt-motion/scripts/motion_render.py`
- Test: `tests/test_motion_render.py`

**Interfaces:**
- Consumes: `pipeline.{manifest,result,schema}`, `brand.generate`.
- Produces:
  - `card_positions(script) -> set` — **chapter `start_beat`s ∪ `{-1}` (outro)** only: exactly the positions `_render` can place. A card confirmed on any other beat is rejected by `validate_plan` up front (not silently dropped at render). Hook `0` excluded by policy.
  - `proposed_motion_json(script) -> list` — one `{"beat": ch["start_beat"], "kind":"card", "template":"card/chapter", "data":{"title": ch["title"]}, "confirmed":False}` per chapter, plus one `{"beat": -1, "kind":"card", "template":"card/outro", "data":{"title": script["title"]}, "confirmed":False}`. **Title lives in `data.title`** (used by scaffold, cache, and renderer).
  - `_init(slug, root="project") -> dict` — writes `motion.json` + runs `brand.generate`; `result.ok`; never marks done.
  - `validate_plan(slug, root) -> list[str]` — loads script + motion.json, calls `schema.validate_motion(motion, card_positions(script))`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_motion_render.py`:

```python
import json
from pipeline import manifest


def _script(d):
    (d / "script.json").write_text(json.dumps({
        "slug": "proj", "title": "Best AI tools", "hook": "h", "outro": "o", "cta": "c",
        "chapters": [{"title": "Pricing", "start_beat": 8}],
        "beats": [{"id": 8, "narration": "n", "b_roll_keywords": ["x"]}],
    }))


def test_init_scaffolds_chapter_and_outro_unconfirmed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = manifest.project_dir("proj")
    _script(d)
    r = mr._init("proj")
    assert r["success"] is True
    m = json.loads((d / "motion.json").read_text())
    beats = {item["beat"] for item in m}
    assert beats == {8, -1}                          # chapter start + outro, no hook
    assert all(item["confirmed"] is False for item in m)
    assert next(i for i in m if i["beat"] == 8)["data"]["title"] == "Pricing"


def test_validate_plan_flags_bad_beat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = manifest.project_dir("proj")
    _script(d)
    (d / "motion.json").write_text(json.dumps(
        [{"beat": 999, "kind": "card", "template": "card/chapter", "confirmed": True}]))
    errs = mr.validate_plan("proj")
    assert any("999" in e for e in errs)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_motion_render.py -k "init_scaffolds or validate_plan" -v`
Expected: FAIL with `AttributeError: module 'motion_render' has no attribute '_init'`.

- [ ] **Step 3: Write the implementation**

Append to `.claude/skills/yt-motion/scripts/motion_render.py`:

```python
from pipeline import manifest, result, schema  # noqa: E402
import brand  # noqa: E402


def _load_script(slug, root):
    return json.loads((manifest.project_dir(slug, root) / "script.json").read_text())


def card_positions(script):
    # Only positions _render can actually place: chapter starts + the outro.
    # (Hook id 0 is excluded by policy; a non-chapter body beat is unplaceable
    # and validation rejects it up front rather than dropping it at render.)
    return {ch["start_beat"] for ch in script.get("chapters", [])} | {-1}


def proposed_motion_json(script):
    out = [{"beat": ch["start_beat"], "kind": "card", "template": "card/chapter",
            "data": {"title": ch.get("title")}, "confirmed": False}
           for ch in script.get("chapters", [])]
    out.append({"beat": -1, "kind": "card", "template": "card/outro",
                "data": {"title": script.get("title")}, "confirmed": False})
    return out


def _init(slug, root="project"):
    script = _load_script(slug, root)
    d = manifest.project_dir(slug, root)
    (d / "motion.json").write_text(json.dumps(proposed_motion_json(script), indent=2))
    brand.generate(slug, root)
    return result.ok(stage="motion",
                     next_action=f"review {d / 'motion.json'}, set confirmed:true, "
                                 f"then run motion_render.py {slug}")


def validate_plan(slug, root="project"):
    script = _load_script(slug, root)
    pj = manifest.project_dir(slug, root) / "motion.json"
    motion = json.loads(pj.read_text()) if pj.exists() else None
    return schema.validate_motion(motion, card_positions(script))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_motion_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/yt-motion/scripts/motion_render.py tests/test_motion_render.py
git commit -m "feat(motion): --init scaffold (chapters+outro via data.title) + validate_plan"
```

---

## Task 8: `_render` — gate, fit, retries, fallback, engine_version, change-gated invalidation

**Files:**
- Modify: `.claude/skills/yt-motion/scripts/motion_render.py`
- Test: `tests/test_motion_render.py`

**Interfaces:**
- Consumes: `motion_fit`, `comp_key`, `validate_plan`, `card_positions`, `pipeline.video_spec`.
- Produces: `_render(slug, force=False, only=None, render_fn=None, engine_version="unset", attempts=2, root="project") -> dict`. Sequence:
  1. skip if `stage_done` and not `force` and `only is None`;
  2. `validate_plan` → `ERR_INVALID_PLAN` on errors;
  3. require `voice` done with non-empty `beat_timings` → `ERR_NO_TIMINGS` ("run yt-voice first");
  4. load motion.json; `partition_confirmed`; `ERR_UNCONFIRMED` (stays pending) if none; filter to `only` when set;
  5. per item: compute render duration by placement (outro=`outro_hold`+`COMP_MIN_S`, capped+warned; chapter=`MOTION_CARD_SEC` if `chapter_fits` else warn+skip→b-roll); compute `comp_key` from template+tokens bytes; **reuse cached** asset when key matches and file exists *and not force*; else render via `_render_with_retries`; on exhausted failure → `ERR_RENDER_FAILED` warning + skip (fallback);
  6. persist `set_stage(... engine="hyperframes", engine_version=..., assets=...)`;
  7. invalidate stitch **only if** the asset set changed vs prior.
- `_render_with_retries(render_fn, item, dur, out_path, attempts) -> None` — calls `render_fn` up to `attempts` times; re-raises the last exception only after all fail.
- Module constants: `COMP_MIN_S=2.0`, `MOTION_CARD_SEC=3.0`, `MIN_FOOTAGE_S=2.0`, `MAX_CARD_S=8.0`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_motion_render.py`:

```python
def _confirm(d, items):
    (d / "motion.json").write_text(json.dumps(items))


def _voice_done(slug, timings):
    manifest.set_stage(slug, "voice", status="done",
                       beat_timings=[{"id": k, "start": 0.0, "end": v}
                                     for k, v in timings.items()])


def _templates_present():
    base = Path(__file__).resolve().parent.parent / ".claude/skills/yt-motion/templates/card"
    base.mkdir(parents=True, exist_ok=True)
    for n in ("chapter.html", "outro.html"):
        p = base / n
        if not p.exists():
            p.write_text("<html><body><h1></h1></body></html>")


def test_render_requires_voice_timings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    r = mr._render("proj", render_fn=lambda *a: None)
    assert r["success"] is False and r["error_code"] == mr.ERR_NO_TIMINGS


def test_render_refuses_unconfirmed_stays_pending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    mr._init("proj")  # all confirmed:false
    r = mr._render("proj", render_fn=lambda *a: None)
    assert r["success"] is False and r["error_code"] == mr.ERR_UNCONFIRMED
    assert manifest.stage_done("proj", "motion") is False


def test_render_outro_card_uses_injected_renderer_and_persists_engine_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    manifest.set_stage("proj", "stitch", status="done")
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    calls = []
    def fake(item, dur, out_path):
        calls.append((item["beat"], dur)); (d / out_path).write_bytes(b"\x00")
    r = mr._render("proj", render_fn=fake, engine_version="hf@sha256:abc")
    assert r["success"] is True and r["rendered"] == 1
    assert calls == [(-1, 6.0)]                       # outro fills its 6s segment
    assert manifest.load("proj")["stages"]["motion"]["engine_version"] == "hf@sha256:abc"
    assert manifest.stage_done("proj", "stitch") is False   # invalidated (changed)


def test_render_long_outro_fills_full_window_not_clamped(tmp_path, monkeypatch):
    # Bug-1 regression: a 15s outro must render a 15s MP4 (== the stitch segment),
    # not an 8s clamp that would freeze for 7s.
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 15.0})
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    seen = []
    def fake(item, dur, out_path):
        seen.append(dur); (d / out_path).write_bytes(b"\x00")
    r = mr._render("proj", render_fn=fake)
    assert seen == [15.0]                              # full window, not 8.0
    assert r["assets"][0]["duration"] == 15.0
    assert any(w["code"] == "motion_card_long" for w in r["warnings"])


def test_render_chapter_too_short_skips_to_broll(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 4.0, -1: 6.0})            # beat 8 too short for 3s flash + footage
    _confirm(d, [{"beat": 8, "kind": "card", "template": "card/chapter",
                  "data": {"title": "Pricing"}, "confirmed": True}])
    r = mr._render("proj", render_fn=lambda *a: None)
    assert r["success"] is True and r["rendered"] == 0
    assert any(w["code"] == mr.ERR_UNFITTABLE for w in r["warnings"])


def test_render_retries_then_falls_back_to_broll(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    n = {"c": 0}
    def boom(*a):
        n["c"] += 1; raise RuntimeError("chrome crashed")
    r = mr._render("proj", render_fn=boom, attempts=2)
    assert n["c"] == 2                                 # retried before giving up
    assert r["success"] is True and r["assets"] == []
    assert any(w["code"] == mr.ERR_RENDER_FAILED for w in r["warnings"])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_motion_render.py -k render -v`
Expected: FAIL with `AttributeError: module 'motion_render' has no attribute '_render'`.

- [ ] **Step 3: Write the implementation**

Append to `.claude/skills/yt-motion/scripts/motion_render.py`:

```python
from pipeline import motion_fit, video_spec  # noqa: E402

COMP_MIN_S = 2.0       # fixed intro+outro of a card comp
MOTION_CARD_SEC = 3.0  # chapter flash length
MIN_FOOTAGE_S = 2.0    # footage that must remain after a chapter flash
MAX_CARD_S = 8.0       # ceiling before a card is treated as a planning error

_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def partition_confirmed(items):
    confirmed = [i for i in items if i.get("confirmed") is True]
    return confirmed, [i for i in items if i.get("confirmed") is not True]


def _durations(slug, root):
    v = manifest.load(slug, root)["stages"].get("voice", {})
    return {t["id"]: round(t["end"] - t["start"], 3) for t in v.get("beat_timings", [])}


def _template_bytes(item):
    p = _TEMPLATES / f"{item['template']}.html"
    return p.read_bytes() if p.exists() else b""


def _render_with_retries(render_fn, item, dur, out_path, attempts):
    last = None
    for _ in range(max(attempts, 1)):
        try:
            render_fn(item, dur, out_path)
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last


def _render(slug, force=False, only=None, render_fn=None, engine_version="unset",
            attempts=2, root="project"):
    if manifest.stage_done(slug, "motion") and not force and only is None:
        return result.ok(stage="motion", skipped="already done")
    errs = validate_plan(slug, root)
    if errs:
        return result.err("invalid motion.json", error_code=ERR_INVALID_PLAN, errors=errs)

    durations = _durations(slug, root)
    if not durations:
        return result.err("no beat_timings — run yt-voice first",
                          error_code=ERR_NO_TIMINGS,
                          next_action="run yt-voice, then yt-motion")

    d = manifest.project_dir(slug, root)
    items = json.loads((d / "motion.json").read_text())
    confirmed, _ = partition_confirmed(items)
    if only is not None:
        confirmed = [i for i in confirmed if i["beat"] == only]
    if not confirmed:
        return result.err("no confirmed motion items", error_code=ERR_UNCONFIRMED,
                          next_action="set confirmed:true in motion.json")

    script = _load_script(slug, root)
    chapter_starts = {ch["start_beat"] for ch in script.get("chapters", [])}
    tokens_bytes = (d / "motion" / "tokens.css").read_bytes() \
        if (d / "motion" / "tokens.css").exists() else b""
    prior = {a["beat"]: a for a in
             (manifest.load(slug, root)["stages"].get("motion") or {}).get("assets", [])}

    assets, warnings = [], []
    for item in confirmed:
        beat = item["beat"]
        if beat == -1:
            hold, warn = motion_fit.outro_hold(COMP_MIN_S, durations.get(-1, 0.0), MAX_CARD_S)
            rdur = round(COMP_MIN_S + hold, 3)   # == outro_s; fills the full window
            if warn:
                warnings.append({"beat": beat, "code": "motion_card_long",
                                 "next_action": f"outro longer than {MAX_CARD_S}s — "
                                                f"sanity-check the card; rendering full length"})
        elif beat in chapter_starts:
            if not motion_fit.chapter_fits(durations.get(beat, 0.0), MOTION_CARD_SEC, MIN_FOOTAGE_S):
                warnings.append({"beat": beat, "code": ERR_UNFITTABLE,
                                 "next_action": "beat too short for a chapter flash; keeps b-roll"})
                continue
            rdur = MOTION_CARD_SEC
        else:  # not a placeable card position (schema should have caught it)
            warnings.append({"beat": beat, "code": ERR_INVALID_PLAN,
                             "next_action": "not a chapter start or outro"})
            continue

        key = comp_key(item, rdur, _template_bytes(item), tokens_bytes, engine_version)
        cached = prior.get(beat)
        out_path = f"media/motion_card_{beat}.mp4"
        if not force and cached and cached.get("comp_key") == key and (d / out_path).exists():
            assets.append(cached)
            continue
        try:
            _render_with_retries(render_fn, item, rdur, out_path, attempts)
        except Exception as exc:  # noqa: BLE001
            warnings.append({"beat": beat, "code": ERR_RENDER_FAILED, "detail": str(exc),
                             "next_action": "keeps b-roll/drawtext; fix template and --force"})
            continue
        assets.append({"beat": beat, "kind": "card", "path": out_path, "duration": rdur,
                       "comp_key": key, "source": "hyperframes"})

    changed = ({(a["beat"], a.get("comp_key")) for a in assets}
               != {(a["beat"], a.get("comp_key")) for a in prior.values()})
    manifest.set_stage(slug, "motion", status="done", engine="hyperframes",
                       engine_version=engine_version, assets=assets)
    if changed:
        manifest.set_stage(slug, "stitch", status="pending")
    return result.ok(stage="motion", rendered=len(assets), assets=assets,
                     warnings=warnings, stitch_invalidated=changed)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_motion_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/yt-motion/scripts/motion_render.py tests/test_motion_render.py
git commit -m "feat(motion): render gate w/ fit, retries, fallback, engine_version, change-gated invalidation"
```

---

## Task 9: Cache skip on normal run, `--force` re-render, `--only`, CLI

**Files:**
- Modify: `.claude/skills/yt-motion/scripts/motion_render.py`
- Test: `tests/test_motion_render.py`

**Interfaces:**
- Produces: `main(argv=None)` — parses `<slug>`, `--init`, `--force`, `--only <beat>`, `--doctor`; default `render_fn=_docker_render`; resolves `engine_version` + `timings`; returns via `result.run`. `--doctor` returns a **non-ok** envelope (and `main` exits non-zero) when tools are missing.
- The cache behavior added in Task 8 already skips unchanged comps on a **normal** run and re-renders under `--force` (the `if not force and cached ...` guard). These tests lock that contract.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_motion_render.py`:

```python
def test_normal_run_skips_unchanged_but_force_rerenders(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    n = {"c": 0}
    def fake(item, dur, out_path):
        n["c"] += 1; (d / out_path).write_bytes(b"\x00")
    mr._render("proj", render_fn=fake)
    mr._render("proj", force=False, render_fn=fake)   # unchanged -> cached
    assert n["c"] == 1
    mr._render("proj", force=True, render_fn=fake)    # force -> re-render
    assert n["c"] == 2


def test_only_renders_single_beat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    _confirm(d, [
        {"beat": 8, "kind": "card", "template": "card/chapter", "data": {"title": "P"}, "confirmed": True},
        {"beat": -1, "kind": "card", "template": "card/outro", "data": {"title": "t"}, "confirmed": True}])
    rendered = []
    mr._render("proj", force=True, only=-1,
               render_fn=lambda i, dur, o: (rendered.append(i["beat"]),
                                            (d / o).write_bytes(b"\x00")))
    assert rendered == [-1]


def test_doctor_cli_exits_nonzero_when_missing(monkeypatch, capsys):
    monkeypatch.setattr(mr.shutil, "which", lambda t: None)  # everything missing
    rc = mr.main(["proj", "--doctor"])
    assert rc != 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_motion_render.py -k "force or only or doctor_cli" -v`
Expected: FAIL — `main` not defined / returns None.

- [ ] **Step 3: Write the implementation**

Append to `.claude/skills/yt-motion/scripts/motion_render.py`:

```python
def _resolve_engine_version():  # pragma: no cover - integration
    """Resolve the pinned HyperFrames Docker image digest. Wired in Task 11."""
    return "unset"


def _docker_render(item, duration, out_path):  # pragma: no cover - integration
    """Drive HyperFrames in Docker to render `item` to `out_path` at `duration`
    seconds, muted+silent-track, video_spec size/fps/pixfmt, color/range tagged."""
    raise NotImplementedError("wired in Task 11 / Phase-0 spike")


def _timings_present(slug, root="project"):
    return bool(_durations(slug, root))


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("slug")
    p.add_argument("--init", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--only", type=int, default=None)
    p.add_argument("--doctor", action="store_true")
    a = p.parse_args(argv)
    if a.doctor:
        d = doctor()
        env = result.ok(**d) if d["ok"] else result.err(d["next_action"], **d)
        result.run(lambda: env, a.slug)
        return 0 if d["ok"] else 1
    if a.init:
        result.run(lambda: _init(a.slug), a.slug)
        return 0
    r = result.run(lambda: _render(a.slug, force=a.force, only=a.only,
                                   render_fn=_docker_render,
                                   engine_version=_resolve_engine_version()), a.slug)
    return 0 if r.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_motion_render.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/yt-motion/scripts/motion_render.py tests/test_motion_render.py
git commit -m "feat(motion): cache skip (normal) + --force re-render + --only + CLI w/ doctor exit code"
```

---

## Task 10: `yt-stitch` consumes motion cards (outro swap + chapter insert)

**Files:**
- Modify: `.claude/skills/yt-stitch/scripts/stitch_video.py` (`_render` load + `plan_segments`)
- Test: `tests/test_stitch.py`

**Interfaces:**
- Consumes: `manifest.motion.assets` (kind `card`).
- Produces: `plan_segments(slug, aspect, script, timings, by_beat, motion_cards=None)`:
  - **Outro swap:** when `t["id"] == -1` and `-1 in motion_cards`, emit a `video` segment with the card MP4, **duration = `mc["duration"]`** (the rendered length, which the renderer set equal to the outro window — stitch must not re-derive it from `dur`). Guarded to `id == -1` so the hook (`id 0`) never swaps.
  - **Chapter insert:** for a body beat whose id is in `motion_cards`, prepend a short `video` segment (the card MP4, its asset `duration`) then the beat's own asset for `dur - card_dur` — mirroring the logo-reveal insert (`stitch_video.py:279-289`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_stitch.py` (match the file's existing imports/helpers):

```python
def test_plan_segments_outro_swap_and_chapter_insert(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    import importlib
    sv = importlib.import_module("stitch_video")
    from pipeline import manifest
    d = manifest.project_dir("proj")
    script = {"hook": "h", "outro": "o", "title": "t",
              "chapters": [{"title": "Pricing", "start_beat": 8}]}
    timings = [{"id": 0, "start": 0.0, "end": 3.0},
               {"id": 8, "start": 3.0, "end": 14.0},     # 11s chapter beat
               {"id": -1, "start": 14.0, "end": 20.0}]   # 6s outro
    by_beat = {8: {"beat": 8, "path": "media/beat_8.mp4", "source": "pexels"}}
    motion_cards = {
        8: {"beat": 8, "kind": "card", "path": "media/motion_card_8.mp4", "duration": 3.0},
        -1: {"beat": -1, "kind": "card", "path": "media/motion_card_-1.mp4", "duration": 6.0}}
    segs = sv.plan_segments("proj", "16x9", script, timings, by_beat, motion_cards)
    # outro is now the motion MP4, not a drawtext card; duration = mc["duration"]
    outro = [s for s in segs if s["id"] == -1]
    assert outro[0]["kind"] == "video" and outro[0]["path"] == "media/motion_card_-1.mp4"
    assert outro[0]["duration"] == 6.0     # mc["duration"], not re-derived from the window
    # chapter beat 8: a 3s card flash THEN 8s of footage
    b8 = [s for s in segs if s["id"] == 8]
    assert b8[0]["path"] == "media/motion_card_8.mp4" and b8[0]["duration"] == 3.0
    assert b8[1]["path"] == "media/beat_8.mp4" and b8[1]["duration"] == 8.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_stitch.py::test_plan_segments_outro_swap_and_chapter_insert -v`
Expected: FAIL — `plan_segments` takes no `motion_cards`.

- [ ] **Step 3: Wire motion cards into `plan_segments`**

In `stitch_video.py`, change the signature and add the two branches. Replace the header line:

```python
def plan_segments(slug, aspect, script, timings, by_beat):
```

with:

```python
def plan_segments(slug, aspect, script, timings, by_beat, motion_cards=None):
    motion_cards = motion_cards or {}
```

Inside the `for t in timings:` loop, in the `id == -1` text-card branch, swap to the MP4 when present. Replace the existing card-emitting block:

```python
        if text is not None:
            tf = cards / f"seg_{t['id']}_{aspect}.txt"
            tf.write_text(_wrap_text(text, 26 if aspect == "9x16" else 42))
            segments.append({"id": t["id"], "kind": "card", "duration": dur,
                             "textfile": str(tf.relative_to(d))})
            continue
```

with:

```python
        if text is not None:
            mc = motion_cards.get(t["id"]) if t["id"] == -1 else None  # hook never swaps
            if mc:   # outro motion card swaps the drawtext card; use its rendered length
                segments.append({"id": t["id"], "kind": "video",
                                 "duration": mc["duration"], "path": mc["path"]})
                continue
            tf = cards / f"seg_{t['id']}_{aspect}.txt"
            tf.write_text(_wrap_text(text, 26 if aspect == "9x16" else 42))
            segments.append({"id": t["id"], "kind": "card", "duration": dur,
                             "textfile": str(tf.relative_to(d))})
            continue
```

Immediately before the final `segments.append(... kind ... path ...)` for body beats (the last line of the loop), add the chapter-insert (mirrors the logo-reveal at lines 279-289):

```python
        mc = motion_cards.get(t["id"])
        if mc and t["id"] not in (0, -1) and dur > mc["duration"]:
            card_dur = round(mc["duration"], 3)
            segments.append({"id": t["id"], "kind": "video",
                             "duration": card_dur, "path": mc["path"]})
            segments.append({"id": t["id"], "kind": kind,
                             "duration": round(dur - card_dur, 3), "path": path})
            continue
        segments.append({"id": t["id"], "kind": kind, "duration": dur, "path": path})
```

In `_render`, load motion cards and pass them in. After the `by_beat = pipeline_assets.merge_assets(...)` line, add:

```python
    motion_assets = (m["stages"].get("motion") or {}).get("assets", [])
    motion_cards = {a["beat"]: a for a in motion_assets if a.get("kind") == "card"}
```

and change the `plan_segments(...)` call to pass `motion_cards`:

```python
        segments = plan_segments(slug, aspect, script, timings, by_beat, motion_cards)
```

- [ ] **Step 4: Run the stitch suite**

Run: `pytest tests/test_stitch.py -v`
Expected: PASS (existing tests + the new one; `@needs_ffmpeg` real-render tests stay skipped if ffmpeg absent).

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/yt-stitch/scripts/stitch_video.py tests/test_stitch.py
git commit -m "feat(stitch): motion cards — outro swap + chapter short-insert (logo-reveal pattern)"
```

---

## Task 11: SKILL.md + Phase-0 alpha spike + real render (integration, manual)

**Files:**
- Create: `.claude/skills/yt-motion/SKILL.md`
- Create: `.claude/skills/yt-motion/templates/card/chapter.html`, `outro.html`
- Modify: `motion_render.py` (`_docker_render`, `_resolve_engine_version`)

**Interfaces:**
- Produces: a working end-to-end render of the outro card + one chapter flash into a final video; a passed Phase-0 alpha-overlay spike that de-risks Phase 2.

> Integration + manual — needs Docker + Node + HyperFrames; cannot run in CI. Deliverable is a verified render + a written spike result, not a unit-test cycle.

- [ ] **Step 1: Install + verify the runtime**

Run: the Docker install block (already provided), then:
Run: `docker run --rm hello-world && node --version && npx hyperframes --version`
Expected: hello-world success, `v22.x`, a HyperFrames version.

- [ ] **Step 2: Author the card comps and lint them**

Write `templates/card/chapter.html` and `outro.html` importing `../tokens.css`, honoring the motion tokens (ease-out only, fade+rise, `document.fonts.ready` before any animation), title from `data.title`. Then gate on lint:
Run: `npx hyperframes lint --json templates/card/chapter.html templates/card/outro.html`
Expected: no errors. Wire this lint call as a pre-render check inside `_docker_render` (fail fast with `ERR_RENDER_FAILED` on lint failure).

- [ ] **Step 3: Phase-0 alpha spike (de-risks Phase 2 — do NOT skip)**

Render a transparent `.mov` (qtrle) via HyperFrames; composite over a test clip:
Run: `ffmpeg -i base.mp4 -i overlay.mov -filter_complex "[0][1]overlay=0:0" -frames:v 1 probe.png`
Open `probe.png`; confirm overlaid pixels **blend** (not opaque, not missing). If alpha fails, STOP and revisit before Phase 2. Lock the Docker image **digest**.

- [ ] **Step 4: Wire `_docker_render` + `_resolve_engine_version`, render the real cards**

Implement `_docker_render(item, duration, out_path)`: lint → drive HyperFrames (template + project `motion/tokens.css`, `data.title`, `video_spec` size/fps/pixfmt, **muted + silent audio track**, color/range tagged `bt709`/`tv`, fonts bundled, `duration` seconds) → write `out_path`. Implement `_resolve_engine_version()` to return the locked image digest from Step 3.
Run the full loop on a real project (voice already done):
Run: `python .claude/skills/yt-motion/scripts/motion_render.py <slug> --init`
Set the outro item and one chapter item `confirmed: true`, then:
Run: `python .claude/skills/yt-motion/scripts/motion_render.py <slug>`
Run: `python .claude/skills/yt-stitch/scripts/stitch_video.py <slug> --force`
Expected: final video shows the animated outro card (filling the outro) and a ~3s chapter flash that cuts to footage; on-brand, legible, navy unshifted vs the b-roll.

- [ ] **Step 5: Write SKILL.md and commit**

Document the loop (init → review motion.json + swatch sheet → confirm → render → `yt-stitch --force`), the `--doctor`/`--only`/`--force` flags, the `motion_*` ERR codes, and the "motion is optional; skip to keep b-roll/drawtext" escape.

```bash
git add .claude/skills/yt-motion/
git commit -m "feat(motion): yt-motion SKILL.md + card comps + Phase-0 alpha spike verified"
```

---

## Roadmap (out of scope — future plans)

- **Phase 2 — `kind: overlay`:** productionize `pipeline/lottie_gen.py` (its consumer lands here), the Lottie→MOV renderer, `assets.overlay_layers()`, and the **post-concat alpha-overlay compositor** in `stitch_video.py` (new filtergraph, alpha-preserving format, `enable` timing). Gated by the Task-11 alpha spike. Includes lower-thirds + source citations (signature Vox element).
- **Phase 3 — `kind: beat`:** full-frame animated D3 data beats (lean on `npx hyperframes add data-chart`), `assets.apply_motion_overrides()` (content override + collision warning), and the chart-legibility spec (type floor, contrast floor, mandatory read-hold). Kinetic typography lands here too.
- **New comp families (no home yet):** animated/annotated **maps** (a defining Vox element — needs its own comp family + plan) and **branded transitions/wipes** between segments (distinct from per-beat cards).

> **Expectation-setting:** this plan delivers the card skeleton. "Vox-style production-grade" is ~80% Phases 2-3 plus the maps family. Foundation shipped ≠ Vox shipped.

### Accepted MVP limitations (deliberate, revisit later)
- **Chapter flash is a fixed `MOTION_CARD_SEC` (3.0s)** regardless of title reading-time. A long chapter title may under-read. Roadmap: derive flash length from title length (within a min/max).
- **Chapters whose opening beat is < `MOTION_CARD_SEC + MIN_FOOTAGE_S` (~5s) get NO card** (skipped with a warning) — so some chapters are announced and some aren't, which can read as inconsistent. Acceptable for MVP; the warning makes it visible to the operator. Roadmap: a fallback (shorter flash, or a thin chapter-label overlay) so every chapter gets *something*.
- **The chapter card head-splits the beat:** the opening ~3s of that beat's narration plays *under* the card before cutting to footage. This is the chosen low-risk model (title over narration-intro usually reinforces), but it's a real aesthetic consequence — confirm it reads well in the Task-11 render and adjust `MOTION_CARD_SEC` if the card lingers over substantive narration.

---

## Self-Review notes

- **Bugs fixed:** (1) outro card now emitted via `proposed_motion_json` targeting `id -1`; (2) `confirmed` validated as `bool` in `validate_motion`; (3) `validate_motion` is called by `validate_plan` inside `_render`; (4) `comp_key` hashes template+tokens bytes; (5) `--force` bypasses the per-item cache (`if not force and cached…`) and the v1 stale-cache test is replaced by `test_normal_run_skips_unchanged_but_force_rerenders`; (6) `engine_version` persisted by `_render`/`_resolve_engine_version`; (7) title flows through `data.title` in scaffold, cache, and renderer.
- **Card model corrected:** cards are segments — outro swap + chapter insert (logo-reveal precedent), not beat overrides. `apply_motion_overrides`/`overlay_layers`/`lottie_gen` deferred to P2/P3 (no Phase-1 consumer).
- **Production hardening folded in:** `video_spec` shared module (Task 1), color/range tagging + fonts + `document.fonts.ready` + silent audio track + lint preflight (Task 11), retries+timeout (Task 8), `MAX_CARD_S` ceiling (Tasks 5/8).
- **Edges:** `--doctor` non-ok envelope + nonzero exit (Task 9); stitch invalidation gated on `changed` (Task 8); voice-missing preflight → `ERR_NO_TIMINGS` (Task 8). (`STOCK_SOURCES` and motion-vs-motion collision live with `apply_motion_overrides` in Phase 3, where that code is built.)
- **Type consistency:** `comp_key(item,duration,template_bytes,tokens_bytes,engine_version)`, `_render(...,only=...,engine_version=...,attempts=...)`, `plan_segments(...,motion_cards=None)`, `outro_hold`/`chapter_fits` signatures match across tasks.

### v2.1 fixes (second review pass)
- **Bug 1 (outro >8s freeze):** `outro_hold` no longer clamps — the outro card fills the full window; `MAX_CARD_S` is warn-only. Stitch outro swap uses `mc["duration"]`, never the re-derived `dur`. Locked by `test_render_long_outro_fills_full_window_not_clamped`.
- **Bug 2 (engine bump didn't bust cache/stitch):** `engine_version` folded into `comp_key`. Locked by the engine-bump case in `test_comp_key_changes_with_template_tokens_duration_and_engine`.
- **Bug 3 (over-permissive validation):** `card_positions` = chapter `start_beat`s ∪ `{-1}` only, so `validate_plan` rejects unplaceable cards up front; the `_render` `else` branch is now defensive/unreachable.
- **Cross-stage contracts verified against real code:** `voice.beat_timings` is a `[{"id","start","end"}]` list (generate_voice.py `concat_timings`); `plan_beats` emits id 0 (hook) and id -1 (outro), so `durations.get(-1)` and chapter-start lookups resolve.
- **Polish:** hook-`0` dropped from all card-position docs + guarded out of the stitch swap; MVP limitations (fixed flash length, sub-5s chapters un-carded, narration-under-card) documented above.
