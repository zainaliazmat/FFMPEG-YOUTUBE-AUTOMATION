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
yt-discover  ->  [GATE 1: topic review]  ->  yt-script  ->  [GATE 2: script approval]  ->  spine
  topics.json                                  draft.json -> script.json                   voice -> media -> captions -> stitch -> out/*.mp4
```

1. **`yt-discover`** -> `project/_discovery/topics.json` (ranked: outlier + commercial-intent).
2. **GATE 1 — topic review (REQUIRED):** present the top topics; the human picks one
   (or approves the top). This is the biggest revenue decision — never auto-select.
3. Picked topic -> **`yt-script`**: research, draft to `project/<slug>/draft.json`,
   run `write_script.py <slug>` until validation is clean -> `project/<slug>/script.json`.
4. **GATE 2 — script approval (REQUIRED):** present the `review_summary` (title, POV,
   chapters, beat count, duration, sources). Call out `verified:false` sources and
   fast-changing facts. **STOP** for explicit approval before any rendering.
5. Approved `script.json` -> **existing spine** -> 16:9 long-form video:
   - `yt-voice/scripts/generate_voice.py <slug>`
   - `yt-media/scripts/fetch_media.py <slug>`
   - `yt-captions/scripts/generate_captions.py <slug>`
   - `yt-stitch/scripts/stitch_video.py <slug> --aspect 16x9`

## File handoffs (single source of truth)
| Stage        | Reads                         | Writes                         |
|--------------|-------------------------------|--------------------------------|
| yt-discover  | `channel.json` (seed_channels)| `project/_discovery/topics.json` |
| yt-script    | `channel.json`, `draft.json`  | `project/<slug>/script.json`, manifest |
| spine        | `project/<slug>/script.json`  | `audio/`, `media/`, captions, `out/*.mp4` |

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
