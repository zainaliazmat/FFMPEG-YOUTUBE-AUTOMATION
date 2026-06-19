# yt-motion — HyperFrames motion-graphics stage

*Design spec · 2026-06-19 · branch `feat/yt-script-phase2`*

## Summary

Add a new optional pipeline stage, **`yt-motion`**, that uses **HeyGen HyperFrames**
(headless Chrome + FFmpeg, deterministic HTML→MP4) as a render engine to produce
**animated** motion-graphics assets — built with **GSAP**, **D3**, and
**Lottie/dotLottie** — that drop into the existing pure-FFmpeg `yt-stitch` step.

The goal is to make the channel's faceless long-form videos feel **alive, modern,
and editorial** without replacing the working FFmpeg assembly path. HyperFrames is
adopted as the **engine**; GSAP/D3/Lottie are the **content** it renders. The stage
emits three kinds of asset and `yt-stitch` consumes them through its existing
asset-merge and overlay machinery.

This is an **additive, opt-in stage behind a human gate** — it does not change the
discover→script→spine contract, the monetization gates, or the FFmpeg render path.

## Goals

- Render **animated** motion graphics (GSAP scenes, animated D3 charts, Lottie
  accents) into the existing pipeline as ordinary beat/overlay assets.
- Keep audio (Kokoro VO, ducking) and captions **entirely in FFmpeg** — motion
  comps are always silent/visual-only.
- Preserve the project's character: pinned/reproducible, idempotent stages,
  human-in-loop gates, fail-fast-before-render.
- Stage the rollout so each phase ships a usable improvement and de-risks the next.

## Non-goals

- **Not** replacing `yt-stitch` or any part of the FFmpeg assembly path.
- **Not** using HyperFrames to render the whole video as one composition — it is
  used only as a per-clip/per-overlay asset generator.
- **Not** authoring 9:16 Shorts variants in the initial phases (16:9 first;
  9:16 is deferred follow-up work).
- **Not** introducing live/network data at render time — all data is baked in at
  author time (matches HyperFrames' determinism model and the channel's
  source-verification gate).

## Decision record

| Decision | Choice | Rationale |
|---|---|---|
| Render engine | **Adopt HyperFrames (option B)** | Solved determinism (GSAP seek-lock, Lottie `setFrame`, ready/font waits), large free catalog as a head start on animated D3, and official Claude Code skills for first-try authoring. Tradeoffs (Node+Chrome runtime, pre-1.0 churn) accepted and mitigated via Docker version pinning. |
| Stage shape | **One stage `yt-motion`** with a per-item `kind` (`card`/`overlay`/`beat`) | Shared renderer; lets the staged rollout enable one `kind` at a time. |
| Beat selection | **New human gate (Gate 4)**, mirroring `yt-capture` | `motion.json` scaffolded with `confirmed:false`; human reviews before render. Preserves monetization discipline. |
| Aspect ratio | **16:9 (1920×1080) first**, 9:16 deferred | Matches primary output; reduces initial scope. |
| Audio | **Always silent comps** | VO/ducking/captions stay in FFmpeg; avoids HyperFrames' audio-ownership clash. |
| Reproducibility | **Pin HyperFrames via Docker image tag** | Neutralizes the pre-1.0 daily-release risk for an unattended pipeline. |

## Architecture

### Pipeline placement

```
discover → [G1 topic] → script → [G2 script] → [G3 products]
        → voice → media → capture → ★ motion (G4) → captions → stitch
```

`yt-motion` runs **after `capture`** (so it can override a beat or layer over its
b-roll) and **after `voice`** (so beat durations come from narration `beat_timings`,
consistent with the rest of the pipeline). It runs **before `captions`/`stitch`**.

### Components

| Component | Path (new unless noted) | Responsibility |
|---|---|---|
| `yt-motion` skill | `.claude/skills/yt-motion/SKILL.md` | Orchestration guide; the two-step init→render contract. |
| `motion_render.py` | `.claude/skills/yt-motion/scripts/motion_render.py` | The stage script: reads `motion.json` + `manifest`, drives HyperFrames per item, writes assets + manifest. Idempotent (`--force`). |
| `brand.py` | `.claude/skills/yt-motion/scripts/brand.py` | One-time generation of `motion/brand.md` (a HyperFrames `frame.md`) + `motion/tokens.css` from `channel.json`. |
| Comp templates | `.claude/skills/yt-motion/templates/` | Brand-locked HyperFrames composition templates per `kind` (card variants, overlay variants, chart variants). |
| `motion.json` | `project/<slug>/motion.json` | Per-project plan of which beats get motion, their kind + template, `confirmed` gate flag. |
| `assets.py` (edit) | `pipeline/assets.py` | Extend merge: `card`/`beat` override; `overlay` adds a layer. |
| `stitch_video.py` (edit) | `.claude/skills/yt-stitch/scripts/stitch_video.py` | New full-frame alpha-overlay compositing path (mirrors the existing PiP overlay path). |

### Data contract

New `manifest.json` stage:

```json
"motion": {
  "status": "done",
  "engine": "hyperframes",
  "engine_version": "<locked image tag>",
  "assets": [
    {"beat": 0,  "kind": "card",    "path": "media/motion_card_hook.mp4",  "comp": "motion/comps/hook/"},
    {"beat": 8,  "kind": "overlay", "path": "media/motion_ovl_8.mov", "framing": "overlay", "alpha": true, "comp": "motion/comps/ovl_8/"},
    {"beat": 12, "kind": "beat",    "path": "media/motion_beat_12.mp4", "source": "hyperframes", "comp": "motion/comps/beat_12/"}
  ]
}
```

Merge rules in `pipeline/assets.py` (the per-beat resolution map):
- `kind: card` / `kind: beat` → **overrides** the beat's asset (same precedence as
  `capture` overriding stock b-roll today).
- `kind: overlay` → **not** an override; recorded as a transparent layer for that
  beat, consumed by `yt-stitch`'s new compositor.

Overlays compose **on top of** whatever asset already won the beat (stock b-roll,
capture PiP, or a motion `beat`).

### `motion.json` (the Gate-4 plan)

```json
[
  {
    "beat": 12,
    "kind": "beat",
    "template": "chart/bar-race",
    "data": { "...": "values baked in at author time" },
    "notes": "China EV share over time",
    "confirmed": false
  },
  {
    "beat": 8,
    "kind": "overlay",
    "template": "overlay/source-citation",
    "lottie": "motion/lottie/check.json",
    "confirmed": false
  }
]
```

Scaffolded by `yt-motion --init` (pre-tagged by `yt-script` motion hints where
available). The human reviews and sets `confirmed: true`. `motion_render.py`
**refuses to render any item with `confirmed: false`** — the same safety pattern as
`yt-capture`.

### Output formats per kind

| `kind` | Format | Notes |
|---|---|---|
| `card` | Solid MP4, 1920×1080, 30 fps, yuv420p, libx264 | Replaces `drawtext` hook/outro/chapter cards; duration from `beat_timings` (ids `0`, `-1`, chapter starts). |
| `overlay` | Transparent `.mov` (qtrle or ProRes 4444) | Lottie icons, lower-thirds, source citations, callouts; composited over the beat's existing video. |
| `beat` | Solid MP4, full-frame, 1920×1080, 30 fps | A whole data/claim beat that *is* an animated D3 chart / GSAP scene. |

All comps render **muted**. Durations are pulled from `manifest.motion`'s source of
truth: the `voice` stage `beat_timings`.

### Brand consistency

`brand.py` generates two artifacts once per project from `channel.json`:
- `motion/brand.md` — a HyperFrames `frame.md`: palette, type scale, motion
  language, do's/don'ts, rewritten "for the camera" (no web chrome).
- `motion/tokens.css` — CSS custom properties (colors, fonts, spacing) imported by
  every comp template so GSAP/Lottie/D3 read as one channel.

Lottie content is sourced from the existing `lottie-master` generator
(`scripts/lottie_gen.py` presets + builder) and free libraries, with **per-file
license recorded** in `manifest` (consistent with `RIGHTS.md` discipline).

### `yt-stitch` changes

1. Accept motion `card`/`beat` MP4s as ordinary beat assets (the segment planner
   already handles MP4 beats — minimal change).
2. **New compositing path** for `overlay` assets: overlay the transparent clip
   full-frame, timed to the beat window, using FFmpeg `overlay` with alpha. This
   mirrors the existing 72% PiP overlay path added for `capture`; it is additive and
   does not touch the default b-roll/Ken Burns/caption paths.

## Reproducibility & runtime

- **New prerequisites:** Node.js 22+, headless Chrome (managed by HyperFrames),
  HyperFrames CLI + skills. FFmpeg 6.1.1 already present.
- **Version pinning:** HyperFrames runs through its **Docker mode** with a pinned
  image tag recorded in `manifest.motion.engine_version`. This is the primary
  mitigation for HyperFrames being pre-1.0 with frequent releases.
- **Idempotency:** `yt-motion` checks `manifest.stage_done(slug, "motion")` and skips
  unless `--force`, consistent with every other stage.
- **Fail-fast:** if Node/HyperFrames/Docker is unavailable, or any `confirmed:false`
  item is encountered, the stage errors before invoking Chrome with a clear message —
  never a cryptic mid-render failure.

## Rollout plan (staged)

### Phase 0 — Spike (de-risk before building)
Throwaway `npx hyperframes init`; render a 5-second clip exercising **GSAP + Lottie +
an animated D3 chart** at 1920×1080/30fps; confirm a transparent `.mov` composites
correctly through FFmpeg `overlay`; lock the Docker image tag. **Gate:** if HF cannot
cleanly produce alpha overlays in this environment, revisit the engine decision before
building the stage.

### Phase 1 — `kind: card` (#3)
Animated hook/outro/chapter cards replace `drawtext` cards. Proves the full
Node+Chrome→MP4→stitch path end to end on the lowest-risk surface. Includes:
`brand.py`, the `yt-motion` skill + `motion_render.py` (card kind only), card
templates, and the minimal `yt-stitch` change to accept motion MP4s.

### Phase 2 — `kind: overlay` (#1)
Lottie/transparent overlays over b-roll. Adds the `yt-stitch` alpha-overlay
compositor, the `assets.py` overlay-layer merge, overlay templates, and Lottie
sourcing via `lottie-master`. Biggest "feels alive" payoff per unit effort.

### Phase 3 — `kind: beat` (#2)
Full-frame animated D3 data beats, built from restyled HyperFrames catalog blocks
(`data-chart`, maps, etc.) brought on-brand via `tokens.css`. Heaviest lift, highest
editorial payoff.

Each phase is independently shippable. The Gate-4 human review and `motion.json`
contract exist from Phase 1; later phases only add new `kind` handlers and templates.

## Risks & mitigations

| Risk | Mitigation |
|---|---|
| HyperFrames pre-1.0 churn breaks renders | Docker image tag pinning; `engine_version` in manifest; Phase-0 spike before commitment. |
| Node+Chrome runtime footprint on Linux | Run via HyperFrames Docker mode; document prereqs; fail-fast if missing. |
| Transparent overlay is a non-default HF path | Validated explicitly in the Phase-0 spike before Phase 2 work begins. |
| Motion graphics look off-brand / spliced-in | `brand.md` + `tokens.css` imported by every comp; human Gate 4 review. |
| Lottie/catalog licensing | Per-file license recorded in manifest; prefer self-generated Lottie via `lottie-master`; reuse `RIGHTS.md` discipline. |
| Render time / memory (frame-by-frame Chrome) | Only short clips/overlays rendered, never the whole video; cap comp complexity per HF guidance (image ≤2× canvas, ≤2–3 blur layers). |

## Open follow-ups (out of scope for this spec)

- 9:16 Shorts variants of motion comps.
- `yt-script` emitting richer motion hints automatically.
- A catalog of reusable channel-branded chart templates beyond the first few.
