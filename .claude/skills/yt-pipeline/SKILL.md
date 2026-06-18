---
name: yt-pipeline
description: The Phase-2 orchestration contract — the canonical discover -> script -> spine order, the two REQUIRED human gates (topic selection, script approval), and the file handoffs between stages. Use to run or reason about the full faceless-video pipeline end to end.
---

# yt-pipeline

The canonical order for turning a niche into a finished long-form video, and the
two human gates that keep it monetizable. Every stage emits the standard
`{"success": bool, "error": ...}` envelope — **check `success` before proceeding.**

## The chain
```
yt-discover -> [GATE 1: topic] -> yt-script -> [GATE 2: script] -> [GATE 3: product URLs] -> spine
  topics.json                      draft.json -> script.json        products.json (confirmed)  capture+voice -> media -> captions -> stitch -> out/*.mp4
```

1. **`yt-discover`** -> `project/_discovery/topics.json` (ranked: outlier + commercial-intent).
2. **GATE 1 — topic review (REQUIRED):** present the top topics; the human picks one
   (or approves the top). This is the biggest revenue decision — never auto-select.
3. Picked topic -> **`yt-script`**: research, draft to `project/<slug>/draft.json`,
   run `write_script.py <slug>` until validation is clean -> `project/<slug>/script.json`.
4. **GATE 2 — script approval (REQUIRED):** present the `review_summary` (title, POV,
   chapters, beat count, duration, sources). Call out `verified:false` sources and
   fast-changing facts. **STOP** for explicit approval before any rendering.
5. **GATE 3 — product URL confirmation (REQUIRED only if the script names products):**
   `yt-capture/scripts/capture_sites.py <slug> --init` writes a proposed
   `products.json`; the human verifies each URL (or adds a press-kit URL / local
   image) and sets `confirmed: true`. Capture refuses unconfirmed entries so a
   wrong/parked domain is never recorded. Skip this gate entirely for scripts with
   no named products. See `yt-capture/SKILL.md` and **read `RIGHTS.md` once**.
6. Approved `script.json` -> **spine** -> 16:9 long-form video:
   - `yt-capture/scripts/capture_sites.py <slug>` (after GATE 3; product beats get
     the real site, the rest keep stock — optional stage, safe to skip)
   - `yt-voice/scripts/generate_voice.py <slug>`
   - `yt-media/scripts/fetch_media.py <slug>`
   - `yt-captions/scripts/generate_captions.py <slug>`
   - `yt-stitch/scripts/stitch_video.py <slug> --aspect 16x9`

## File handoffs (single source of truth)
| Stage        | Reads                         | Writes                         |
|--------------|-------------------------------|--------------------------------|
| yt-discover  | `channel.json` (seed_channels)| `project/_discovery/topics.json` |
| yt-script    | `channel.json`, `draft.json`  | `project/<slug>/script.json`, manifest |
| yt-capture   | `script.json`, `products.json`| `media/product_*.png`, manifest `stages.capture` |
| spine        | `script.json`, manifest assets| `audio/`, `media/`, captions, `out/*.mp4` |

## Rules
- **Both gates are mandatory.** The human approval gate is load-bearing for YouTube's
  July-2025 inauthentic-content policy, not optional.
- Each stage is idempotent (`--force` to re-run) and never raises to its caller; it
  writes its envelope to stdout and `project/<slug>/.result.json`.
- Treat discovery output as candidates for human judgment, not gospel — the outlier
  bands and commercial-intent flag are heuristics.

## Validation
- Hermetic handoff (topic -> draft -> valid script.json) is covered by
  `tests/test_integration.py`.
- The full discover->render path is run manually with live keys, gated behind
  `YT_RUN_LONGFORM_RENDER=1` (`tests/test_longform_render.py`).
