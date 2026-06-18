# Phase 2 — The Revenue Engine: Implementation Report

**Branch:** `feat/yt-script-phase2`
**Date:** 2026-06-18
**Scope:** `yt-script` (long-form scriptwriting) + `yt-discover` (topic outlier scoring) + integration, on top of the verified Phase-1 render spine.

---

## 1. Executive summary

Phase 2 is implemented, tested, and committed across 5 logical commits. The two
revenue stages now exist:

- **`yt-script`** turns a chosen topic into a validated, long-form (8-20 min),
  cited, POV-driven `script.json` the existing spine consumes — behind a required
  human approval gate.
- **`yt-discover`** scores seed-channel videos by median-based outlier to surface
  proven, advertiser-friendly topics — behind a required human topic-selection gate.
- **Integration** wires `discover -> script -> spine` with both gates documented in
  a single orchestration contract.

**Test status:** `100 passed, 1 skipped` (the skip is the live render stress test,
which is opt-in). 30 new tests added, all discriminating (they fail on a
non-compliant input, not just smoke-run).

**Spine-at-scale:** validated live at **31 beats / ~10.9 min** — see §4.

---

## 2. What was built (by task)

### Task 1 — long-form schema + validator + channel config
- `pipeline/longform.py`: `word_count`, `estimate_duration_min`, and
  `validate_longform_script` (reuses the spine's `schema.validate_script` for the
  base contract, then enforces: duration in channel range, >=4 chapters, >=1
  midroll beat, >= `min_sources` cited sources, non-empty per-video `channel_pov`,
  unique positive-integer beat ids).
- `channel.json`: added `wpm: 140`, `min_sources: 5`, `seed_channels: []`.
- `fixtures/longform_script.json`: a compact valid long-form fixture for unit tests.
- `tests/test_longform_schema.py` (13 tests): each validation test flips exactly one
  field on a known-good fixture and asserts the matching error — duration too
  short/long, 2 chapters, empty midroll, 4 sources, empty POV, duplicate id,
  non-positive id — plus the backward-compat cross-check (base `validate_script`
  still returns `[]` on the richer fixture) and the pure math.

### Task 2 — `yt-script` writer + SKILL.md
- `.claude/skills/yt-script/scripts/write_script.py`: `assemble_script` (computes
  word_count + duration), `review_summary` (the approval-gate summary, marks
  `[UNVERIFIED]` sources), and the CLI (`<slug>`: reads `draft.json`, validates,
  writes `script.json` only if compliant, inits manifest, prints envelope + summary).
- `.claude/skills/yt-script/SKILL.md`: the retention framework (hook / context
  bridge / 3-6 segments with open loops / midroll placement / re-hook / CTA /
  pacing), the non-negotiable POV + authenticity rules (never fabricate; sources
  `verified:false`; flag fast-changing facts), and the 4-step process ending at the
  **human approval gate**.
- `tests/test_write_script.py` (5 tests): word/duration math, draft-wpm override,
  review-summary completeness, CLI rejects a non-compliant draft with the
  validator's errors (and writes no `script.json`), CLI accepts a compliant draft.

### Task 3 — long-form stress test
- `fixtures/longform_draft.json`: a genuine **31-beat, ~10.9 min** AI-tools draft
  ("The AI Productivity Stack"), on-channel POV, 8 chapters, 2 midroll points, 6
  cited sources (all `verified:false`).
- `tests/test_longform_render.py`: gated behind `YT_RUN_LONGFORM_RENDER=1`. Drives
  the real spine (script -> voice -> media -> captions -> stitch), asserts the
  `filter_complex` survives 30-40 inputs, ffprobe shows 1920x1080 / yuv420p /
  duration in 8-20 min, and reports per-stage + total wall-clock.

### Task 4 — `yt-discover`
- `.claude/skills/yt-discover/scripts/discover.py`: pure functions
  (`parse_iso8601_duration`, `is_short`, `uploads_playlist_id`, `median`,
  `outlier_score`, `views_per_hour`, `rank_videos`, `commercial_intent_flag`) plus
  the IO wrapper (cheap enumeration: channels.list -> uploads playlist -> playlistItems
  -> videos.list by 50; avoids the 100-unit `search.list`; 429/5xx backoff; casts
  viewCount, skips hidden stats).
- `.claude/skills/yt-discover/SKILL.md`: setup (API key + seed channels), the quota
  math, the scoring method, the 3x/10x thresholds, and the Gate-1 handoff.
- `tests/test_discover.py` (9 tests): all duration/boundary/median/div-by-zero/vph
  cases, plus `rank_videos` filtering+sorting and the recent-from-baseline exclusion.

### Task 5 — integration
- `.claude/skills/yt-pipeline/SKILL.md`: the canonical `discover -> [Gate 1] ->
  script -> [Gate 2] -> spine` order, the file-handoff table, and the rule that both
  gates are mandatory.
- `tests/test_integration.py` (2 tests): hermetic topic -> draft -> `write_script.py`
  -> valid `script.json` (asserts both `validate_longform_script` and base
  `validate_script` pass), and that `assemble_script` is pure/idempotent (safe to
  call before the gate).

---

## 3. Decisions made (autonomous, "all recommended")

1. **Branch:** stayed on the existing `feat/yt-script-phase2` (already cut from the
   Phase-1 work) rather than creating a second branch — the work is the same stack.
2. **`channel.json` already existed** (richer than the plan's literal example, with
   `pacing_wpm` range and fuller authenticity rules). Kept it and only *added* the
   fields the validator/discover read (`wpm`, `min_sources`, `seed_channels`). The
   validator defaults already matched, so this is belt-and-suspenders.
3. **Two fixtures, not one:** a compact `longform_script.json` for fast validator
   unit tests (declares duration directly), and a real 31-beat `longform_draft.json`
   for the CLI accept test + the live stress render (so the recomputed duration is
   genuinely in range). This is why the CLI accept test uses the draft, not the
   compact fixture.
4. **`rank_videos` baseline includes sub-floor flops.** A channel's low-view
   long-form uploads are real baseline data and correctly lower the median, making
   true outliers stand out. Only Shorts and *recent* videos are excluded from the
   baseline. (A test initially encoded the wrong expectation here; the code was
   correct and the test was fixed, not the code.)
5. **No spine changes.** The stress test proved the spine handles scale (§4), so the
   "only touch the spine if it chokes" escape hatch was not needed.

---

## 4. Long-form stress-test findings (spine at scale)

The deferred Phase-1 validation: does the spine survive real long-form scale? It
was run **live, end to end** on the 31-beat draft.

**Verdict: YES — the spine survives 31-beat scale, unchanged.** The single FFmpeg
`filter_complex` handled all 31 inputs in one graph with no error and no limit hit.
Segment-and-concat assembly was **not** needed.

**Output (ffprobe-verified):**
| Check | Result |
|-------|--------|
| Resolution | 1920×1080 ✓ |
| Pixel format | yuv420p ✓ |
| Duration | 538.1s = **8.97 min** (in 8-20 target) ✓ |
| faststart | moov before mdat ✓ |
| Audio | present, non-silent ✓ |
| File size | 114 MB |

**Wall-clock (first full render, cold, single CPU box):**
| Stage | Time | Note |
|-------|------|------|
| write_script | 0.1s | assemble + validate |
| voice (Kokoro TTS) | 922s (15.4 min) | 31 beats / 1,526 words |
| media (Pexels+Pixabay) | 292s (4.9 min) | 31 keyword searches + downloads |
| captions (WhisperX, CPU) | 214s (3.6 min) | word-level on ~9 min audio |
| stitch (FFmpeg) | 803s (13.4 min) | 31-input filter_complex, 1080p |
| **total** | **2,231s (37.2 min)** | **≈4.1× the 9-min video length** |

**Practicality finding:** correct at scale, but **slow on CPU** — ~37 min to
render a 9-min video. The two dominant costs are Kokoro TTS (~15 min) and the
FFmpeg render (~13 min). Per the plan, this is a *finding*, not a trigger to
pre-optimize: for volume, the levers are a GPU (TTS + encode) or parallelizing the
per-beat TTS — to be decided when throughput actually matters, not now. The
correctness goal (does long-form assemble without choking?) is met.

**Test note:** the first run exposed a bug in the test's `_ffprobe` helper (it
passed two `-show_entries` tokens; FFprobe read the second as an input file →
empty output). Fixed to join sections with `:`. The render itself was correct
throughout. The test is now idempotent — it reuses an existing render and
re-validates in ~10s, so only a fresh project pays the full render cost.

---

## 5. Honest caveats (carried from the plan, still true)

- **Script quality depends on real research.** This run drafted from knowledge, so
  every source is `verified:false` and fast-changing facts are flagged. The human
  approval gate is load-bearing, not decorative.
- **`yt-discover` is unproven against a live key.** Its pure scoring functions are
  fully tested, but the end-to-end API path needs a `YOUTUBE_API_KEY` (absent from
  `.env` — the human must provide it) and real `seed_channels` (currently `[]`).
  Until then, `discover()` returns a clean error envelope, by design.
- **Thresholds are heuristics.** Outlier bands (3x/10x) and the keyword-based
  `commercial_intent_flag` produce candidates for human judgment, not verdicts.
- **The UC->UU uploads-playlist shortcut** is a convention; the code keeps the
  `channels.list` fallback.

---

## 6. What the human still needs to provide

1. **`YOUTUBE_API_KEY`** in `.env` (Google Cloud -> enable YouTube Data API v3 ->
   API key) to activate `yt-discover`.
2. **`seed_channels`** in `channel.json` (3-8 strong niche channels, `UC...` ids).
3. Until discover is live, **hand-pick the topic** for each `yt-script` run.

---

## 7. Verification evidence

- Full suite: `100 passed, 1 skipped` (the skip is the opt-in live render).
- New tests are discriminating: each validator/ranking test flips one field and
  asserts the specific error/exclusion, so a no-op implementation fails them.
- New modules compile clean; `discover` error paths (`no key`, `no seeds`) return
  clean `{"success": false, ...}` envelopes.
- Commits (5): long-form schema -> yt-script -> stress test -> yt-discover -> integration.
