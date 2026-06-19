<!-- /autoplan restore point: /home/zain-ali/.gstack/projects/FFMPEG-YOUTUBE-AUTOMATION/feat-yt-script-phase2-autoplan-restore-20260619-131806.md -->
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

<!-- ============================================================= -->
<!-- /autoplan REVIEW — appended 2026-06-19 -->
<!-- ============================================================= -->

## /autoplan — Phase 1: CEO Review

### CEO dual voices — consensus table

| Dimension | Claude | Codex | Consensus |
|---|---|---|---|
| 1. Premises valid (motion moves retention here)? | NO | NO | DISAGREE w/ plan |
| 2. Right problem to solve? | NO | NO | DISAGREE w/ plan |
| 3. Scope calibration (Phase 1 cost) correct? | NO | NO | DISAGREE w/ plan |
| 4. Alternatives sufficiently explored? | NO | NO | DISAGREE w/ plan |
| 5. Vendor/competitive risk covered? | Partial | Partial | CONFIRMED risk real |
| 6. 6-month trajectory sound? | NO | NO | DISAGREE w/ plan |

Both voices reviewed independently (Codex from context only — repo sandbox blocked it)
and converged on every major point. High-confidence signal.

### Premise challenge (the load-bearing assumption)

**Stated/assumed premise:** "Animated motion graphics meaningfully improve retention
and subscribers for this analytical AI-tools-review niche — enough to justify adding a
Node 22 + headless-Chrome + Docker + pre-1.0-vendor (HyperFrames) stack to a clean
Python+FFmpeg pipeline."

This premise is **never stated or tested** in the spec. The channel's own positioning is
"honest, data-backed verdicts — substance over polish," which is an *anti-polish* stance.
For analytical/explainer channels the dominant retention levers (hook, script density,
pacing, thumbnail/title CTR, evidence visuals) are cheaper and better-evidenced than
motion polish. → **Requires human confirmation (premise gate).**

### Grounded facts that sharpen the challenge
- **Docker is NOT installed** on this machine (`docker: command not found`), yet
  Docker-image-pinning is the spec's *primary* reproducibility mitigation. The
  load-bearing risk control is not available in the operating environment.
- **`lottie_gen.py` is untracked** (`?? "Lottie & dotLottie research/"`, two divergent
  copies) and **emits Lottie JSON only — it does not render video.** So "reuse the
  existing lottie-master generator" understates real integration work, and the channel
  still needs *some* Lottie→MOV renderer regardless of engine choice.
- Node 22 is present (nvm-managed user-local — itself a fragility for unattended runs).

### What both voices recommend (User Challenge — not auto-decided)
1. **Prove the premise cheaply first** — hand-make 2-3 motion beats for ONE existing
   video (any throwaway tool), ship it, read the retention-graph delta. Attach a kill
   metric. No engine work until motion is shown to move *your* numbers.
2. **Invert the rollout** — if motion is worth doing, do **overlays first** (the spec's
   own admitted highest payoff-per-effort), not cards (lowest-value surface paying the
   entire infrastructure bill).
3. **Score the lighter engines** the spec skipped: FFmpeg-native motion (zoompan/
   drawtext-alpha/xfade/geq — already used in `stitch_video.py`), `lottie_gen` + a tiny
   `rlottie`/`lottie2gif` renderer, or **Remotion** (stable, 1.0+) before a pre-1.0 vendor.
4. **Keep `drawtext` cards forever** — they're free and already work.

### Implementation alternatives table (the missing 0C-bis)

| Approach | Operator burden | Reproducibility | "Feels alive" payoff | New infra |
|---|---|---|---|---|
| A. FFmpeg-native only (zoompan/drawtext-alpha/xfade/geq) | Lowest (stack unchanged) | Deterministic by construction | Med (60-70%) | None |
| B. `lottie_gen` + tiny Lottie→MOV renderer (rlottie) | Low-med | Deterministic | Med-high (overlays) | 1 small lib |
| C. Remotion (React→MP4) | Med (Node+Chrome, but stable 1.0+) | Good (pinned npm) | High | Node+Chrome |
| D. HyperFrames (spec's choice) | High (Node+Chrome+Docker+pre-1.0 vendor) | Pin papers over Chrome nondeterminism | High | Node+Chrome+Docker+vendor |

CEO recommendation: **B or C beat D for a solo unattended pipeline** until D's payoff is
proven to exceed them. Surfaced to the operator as a User Challenge.

### NOT in scope (CEO)
- 9:16 Shorts (already deferred by spec — agree).
- Live/network data at render time (correctly excluded).

### What already exists (leverage map)
- FFmpeg alpha/overlay/`geq` rounded-corner masking + `zoompan` Ken Burns —
  `.claude/skills/yt-stitch/scripts/stitch_video.py` (animated compositing already shipping).
- Per-beat asset reconciliation + capture-wins precedence — `pipeline/assets.py`.
- Human-gate + `confirmed:false` refusal pattern — `.claude/skills/yt-capture/`.
- Lottie JSON generation (untracked, JSON-only) — `Lottie & dotLottie research/`.

## /autoplan — Phase 2: Design Review

Voices: Claude subagent (grounded). Codex **[codex-unavailable: sandbox bwrap failure]**.
Single-reviewer mode for this phase. These findings apply to ANY engine (they are not
HyperFrames-specific) — directly relevant since the operator chose to keep HyperFrames.

### Design litmus scorecard (plan's design completeness, 0-10)

| Dimension | Score |
|---|---|
| 1. Visual system defined | 1/10 |
| 2. Motion language specified | 0/10 |
| 3. Cross-tech consistency | 3/10 |
| 4. Card design intent | 2/10 |
| 5. Timing-fit / states | 1/10 |
| 6. Chart legibility | 1/10 |

### Findings (auto-decided unless marked TASTE)

**D-F1 (CRITICAL) — The design system is conjured from nothing.** `channel.json` contains
zero visual tokens (no palette, type scale, spacing, or motion values). The only existing
visual language is `CARD_BG="0x0b1a2a"` (navy) + DejaVu Sans Bold in `stitch_video.py`.
"`brand.py` generates `brand.md`+`tokens.css` from `channel.json`" therefore means an LLM
*improvises* a brand identity per project, non-deterministically — the opposite of
"brand-locked." → **DECISION: ACCEPT FIX (structural).** Author `tokens.css`+`brand.md`
**by hand once, committed in the skill** (not generated, not per-project): anchor on the
`#0b1a2a` navy + 1 accent + neutral ramp + 1 "verdict" semantic color; one type pairing;
4/8px grid. `brand.py` shrinks to *injecting* the fixed system + per-project copy only.
Human approves a static swatch sheet before any render. [P1 completeness, P5 explicit]

**D-F2 (CRITICAL) — Zero motion language specified.** "alive/modern/editorial" is a vibe,
and likely the *wrong* one for a "calm, specific, slightly skeptical" voice — springy/
overshoot motion reads as the hype-merchant the channel positions against. → **DECISION:
ACCEPT FIX (structural).** Commit motion tokens: one ease-out family (no bounce/elastic/
overshoot — banned list); durations entrance 400-600ms, emphasis 250ms, exit 300ms (floor
200ms, ceiling 800ms); one-primary-element-at-a-time restraint rule; single entrance/exit
grammar (fade + 24px rise). Brand statement: "motion confirms, it doesn't sell." [P1, P5]

**D-F3 (HIGH) — Three animation stacks splice.** GSAP templates + restyled HyperFrames-
catalog D3 + free-library Lottie = three aesthetic origins. `tokens.css` enforces color/
font only — NOT motion personality, stroke weight, corner radius, icon style. Lottie is
worst (baked-in third-party easing). → **DECISION: ACCEPT FIX.** Commit a visual style
spec (stroke/radius/flat-no-gradient/icon grid); generate a small *owned* Lottie set via a
productionized `lottie_gen` rather than free libraries; re-time Lottie easing to motion
tokens; add a Gate-4 human side-by-side "same channel?" check. [P1]

**D-F4 (HIGH) — No card design intent; animation may hurt the hook. [TASTE DECISION]**
The hook card has ~1.5s to land while the viewer decides to stay; type assembling itself
on-screen costs legibility at the exact wrong moment. Structural floor (non-negotiable):
hook type must be fully legible at frame 0. The taste call: **animate the hook at all, or
keep static `drawtext` for the hook permanently?** → **RECOMMEND: keep hook static
`drawtext` (legibility + free), animate only chapter/outro cards** [P5 explicit]. Surfaced
at gate.

**D-F5 (HIGH) — Timing-fit unspecified; will visibly break.** Comp natural length vs
narration `beat_timings` are never reconciled. Short comp → frozen end-state = dead air;
long comp → hard-cut mid-animation = amputation. `stitch_video.py`'s `tpad=clone`/`-t trim`
machinery is correct for b-roll and *exactly wrong* for motion (freezes/amputates). →
**DECISION: ACCEPT FIX (structural; also an Eng data-contract gap).** Author comps as
`intro → elastic-hold → outro`; renderer receives beat duration and stretches the HOLD only;
declare min/max servable beat-duration per kind; scaffolder refuses to place a comp that
can't fit and falls back to b-roll. [P1]

**D-F6 (HIGH) — Chart legibility unaddressed for a "concrete numbers" channel.** Phase-3
animated D3 (bar-race example is worst case) on phones at 1.5× has no still moment to read
the number. Catalog charts use desktop label sizes, low-contrast series, too many marks. →
**DECISION: ACCEPT FIX.** Add chart legibility spec: min on-screen type size legible at
360px-wide playback; contrast floor for marks vs card bg; hard cap on simultaneous series;
**mandatory read-hold** (final number large + static ≥2.5s). Prefer count-up-to-held-value
over bar-race; ban charts where the payload number is never static. Ties to D-F5's elastic-
hold. [P1]

### Design through-line
F1+F2 are the root: there is no committed visual or motion system, only a promise to
generate one from a source that contains none. F3/F4/F6 are downstream consistency/intent/
legibility symptoms with nothing to enforce against; F5 is an independent mechanical gap.
**Recommendation: author + commit + human-approve the static brand+motion artifact BEFORE
building render infra** — this is engine-independent and the single highest-leverage fix.

## /autoplan — Phase 3: Eng Review

Voices: Claude subagent (grounded, read all referenced code). Codex
**[codex-unavailable: sandbox bwrap failure]**. Single-reviewer mode.
Test plan artifact written to:
`~/.gstack/projects/FFMPEG-YOUTUBE-AUTOMATION/zain-feat-yt-script-phase2-test-plan-20260619-134215.md`

### Eng dual voices — consensus table

| Dimension | Claude | Codex | Consensus |
|---|---|---|---|
| 1. Architecture sound? | Partial — 2 "minimal" claims are actually new arch | N/A | subagent-only |
| 2. Test coverage sufficient? | NO — spec ships zero test plan | N/A | subagent-only |
| 3. Performance risks addressed? | Partial — per-comp Chrome cost, no per-item cache | N/A | subagent-only |
| 4. Security threats covered? | N/A — local pipeline, no new attack surface | N/A | subagent-only |
| 5. Error paths handled? | NO — preflight/fail-fast gaps for unattended | N/A | subagent-only |
| 6. Deployment risk manageable? | NO — Docker absent, nvm-node non-interactive | N/A | subagent-only |

### Architecture — new asset flow (ASCII)

```
                   voice.beat_timings (durations, source of truth)
                                 │
 media (stock) ─┐                ▼
 capture (PiP) ─┼──► merge_assets() ──► by_beat {beat: base_asset}     ← FLAT MAP (today)
 motion card/ ──┘     (override chain:                │                    keep backward-compat
   beat               motion > capture > stock)       │
                                                       ▼
 motion overlay ─► overlay_layers() ─► {beat:[ovl,…]} │   ← NEW separate fn (E-F1)
   (.mov, alpha)                            │          │
                                            ▼          ▼
                            plan_segments(…, by_beat, overlays=…)
                                            │
                       build_command: concat [v0][v1]…[vbg]
                                            │
                       NEW post-concat stage:                          ← NEW arch (E-F3)
                       [vbg][ovlN]overlay=0:0:enable='between(t,s,e)'  (alpha-preserving
                                            │                            format, NOT _norm)
                                            ▼
                              burn captions → output yuv420p
```

### Findings (auto-decided unless marked TASTE)

**E-F1 (HIGH) — Merge return-shape change is real, unspecified, breaks the consumer.**
`assets.py:33-40` returns a FLAT `{beat_id: asset}`; `plan_segments` (`stitch_video.py:265`)
reads one asset per beat. Overlays are a parallel LAYER, not an override — a flat dict can't
carry base + overlays for one beat. Spec only says "extend merge" with no signature. All 5
`test_assets.py` cases assert the flat shape. → **DECISION: ACCEPT FIX.** Keep `merge_assets`
flat + override-only (card/beat); add a SEPARATE `overlay_layers(motion_assets) ->
{beat_id:[…]}`; `plan_segments` gains one optional `overlays=None` param. Isolates the
breaking change; existing tests + contract stay intact. [P4 DRY, P5 explicit]

**E-F2 (HIGH) — Capture-vs-motion precedence on the same beat is undefined. [TASTE]**
`merge_assets` resolves precedence by insertion order (`assets.py:37-40`). With motion added,
a beat with BOTH a confirmed capture PiP and a confirmed motion comp has no defined winner —
one human-confirmed asset is silently dropped either way. Both are human-confirmed, so neither
is obviously subordinate. → **RECOMMEND: motion beat/card > capture > stock** (motion is the
most deliberate authored asset) **+ emit a collision warning** (mirror `capture_sites.py:453`)
so a dropped asset is never silent. Reasonable people could pick capture > motion (a real
product screenshot may beat a generic motion comp). Surfaced at gate as a small taste call.

**E-F3 (HIGH) — The overlay compositor is genuinely NEW work; "mirrors existing PiP" is
false.** `build_command` (`stitch_video.py:169-212`) is a pure CONCAT timeline; no path
overlays a clip on top of a running beat. `product`/PiP (`:147-159`) is a standalone
`pad`-onto-card replacement; `_logo_card` (`:74-103`) bakes a single PNG with `-frames:v 1`.
The motion overlay (transparent VIDEO over a playing beat, timed to the window) has no analog.
→ **DECISION: ACCEPT FIX.** Rewrite spec §yt-stitch item 2 to state this is a new filtergraph
stage; specify **post-concat overlay** with `enable='between(t,start,end)'` (keeps default
b-roll/Ken-Burns path untouched); specify overlay-length-vs-beat reconciliation distinct from
b-roll's clone-pad. [P5 explicit, P1 completeness]

**E-F3b (MEDIUM) — `.mov` alpha is destroyed by `_norm`'s yuv420p.** `_norm` (`stitch_video.py:65`)
forces `format=yuv420p` (no alpha plane) in every chain; if the overlay clip passes through it,
transparency is gone before `overlay` runs. → **DECISION: ACCEPT FIX.** Overlay input uses an
alpha-preserving chain (qtrle→rgba / ProRes4444→yuva444p10le), NOT shared `_norm`; Phase-0
spike must probe that overlaid pixels actually BLEND, not just that ffmpeg exits 0. [P1]

**E-F4 (HIGH) — `"motion"` missing from `manifest.STAGES`; `manifest.py` omitted from
Components.** `manifest.py:11` STAGES has no "motion", so `init()` (`:40-41`) never seeds it
and the tuple is stale as an ordering/listing source. Spec Components table (lines 69-78)
never lists `manifest.py`. → **DECISION: ACCEPT FIX.** Add `manifest.py` to Components; add
`"motion"` to STAGES in pipeline order; add `test_motion_is_a_known_stage`
(mirror `test_manifest.py:34-37`). [P5 explicit — clearly right]

**E-F5 (HIGH) — Unattended fail-fast gaps.** (1) Docker is the primary mitigation but is NOT
installed. (2) Node is nvm-managed — a non-interactive/cron `subprocess` call gets
`node: command not found` unless the absolute nvm path is resolved or env sourced. (3)
HyperFrames Chrome is net-new runtime (capture uses Playwright Chromium — no reuse). →
**DECISION: ACCEPT FIX.** Add preflight checks before any Chrome call: resolve absolute
node path or require system node; `shutil.which("docker")` with typed error; HF version
probe — typed `ERR_*` codes like `capture_sites.py:44-49`. Daemon must be
`systemctl enable --now docker` for unattended runs. [P1 completeness]

**E-F6 (MEDIUM) — Idempotency caching granularity + downstream invalidation undefined.**
Motion renders MANY expensive Chrome comps but only stage-level `stage_done`; `--force`
re-renders ALL. Re-running motion doesn't invalidate `stitch` (`stitch_video.py:303` skips if
done). Re-running voice shifts `beat_timings` but already-rendered comps keep stale duration
with no detection. → **DECISION: ACCEPT FIX.** Per-comp cache key (template+data+beat-duration
hash) in `manifest.motion.assets[]`; motion re-render clears `stages.stitch.status`. [P1]

**E-F7 (HIGH) — Spec ships zero test plan.** → **DECISION: ACCEPT FIX.** 13-row coverage map
written to the test-plan artifact (path above). Split `motion_render.py` so pure parts
(plan/fit/merge/gate/manifest/cache) are unit-tested; only HTML→MP4 needs the integration
harness. Add a `@needs_docker`/`@needs_node` skip analog to `@needs_ffmpeg`. [P1]

### NOT in scope (Eng)
- Rewriting the proven flat-map merge contract (we wrap, not replace — E-F1).
- A full Chrome-render CI harness (out of blast radius; document as integration-only).

### What already exists (Eng leverage map)
- `--init`/`--force`/`confirmed:false` refusal + typed `ERR_*` — `capture_sites.py`.
- `stage_done`/`set_stage` idempotency — `manifest.py`.
- `@needs_ffmpeg` real-render test pattern — `tests/test_stitch.py:17,296-314`.
- Concat filtergraph + `geq` alpha + `zoompan` — `stitch_video.py`.

### Failure modes registry (critical gaps flagged ⚠)

| Failure mode | Detected? | Fix owner |
|---|---|---|
| ⚠ Overlay alpha silently flattened by `_norm` yuv420p | NO (today) | E-F3b + spike |
| ⚠ Human-confirmed asset dropped on capture/motion collision | NO | E-F2 |
| ⚠ Unattended run: `node`/`docker` not on PATH | NO | E-F5 |
| ⚠ Stale comp duration after voice re-run | NO | E-F6 |
| Motion comp shorter/longer than beat (dead air / amputation) | NO | D-F5 |
| confirmed:false rendered | YES (spec refuses) | already specified |

## /autoplan — Phase 3.5: DX Review

Voices: Claude subagent (grounded). Codex **[codex-unavailable: sandbox bwrap failure]**.
Single-reviewer mode. The "developer" = the solo operator running the pipeline by hand.

### DX dual voices — consensus table

| Dimension | Claude | Codex | Consensus |
|---|---|---|---|
| 1. Getting started < 5 min? | NO — Docker absent, unguided | N/A | subagent-only |
| 2. API/CLI naming guessable? | YES — transfers from capture | N/A | subagent-only |
| 3. Error messages actionable? | NO — only "clear message" promised | N/A | subagent-only |
| 4. Gate/preview reviewable? | NO — confirms sight-unseen | N/A | subagent-only |
| 5. Iteration loop tolerable? | NO — --force re-renders all comps | N/A | subagent-only |
| 6. Failure recovery safe? | NO — failed override can break stitch | N/A | subagent-only |

### DX scorecard (0-10)

| Dimension | Score |
|---|---|
| Getting-started | 3/10 |
| Error quality | 3/10 |
| Naming consistency | 8/10 |
| Preview/confirm UX | 2/10 |
| Iteration loop | 3/10 |
| Failure recovery | 4/10 |

### Developer (operator) journey map

| Stage | Operator action | Friction |
|---|---|---|
| 1 Install Node 22 | (present) | unknown without a check |
| 2 Install Docker | OS-level install | ⚠ ABSENT — multi-step, no guide |
| 3 Install HyperFrames CLI | npx/global | net-new |
| 4 Install HF Claude Code skills | per HF docs | net-new |
| 5 `yt-motion <slug> --init` | scaffold motion.json | mirrors capture ✓ |
| 6 Gate 4 review | set confirmed:true | ⚠ BLIND — no preview |
| 7 `yt-motion <slug>` render | drives HyperFrames | heavy Chrome render |
| 8 `yt-stitch --force` | re-pull motion assets | ⚠ unspecified as part of loop |
| 9 Watch → find a bad comp | — | — |
| 10 Tweak + `yt-motion --force` | re-render | ⚠ re-renders ALL comps |

**TTHW: ~9-12 steps first-run (cold), ~5 warm. vs capture ~3 steps.** Materially heavier.

### Findings (all auto-decided — clearly-right, consistent with the repo's own patterns)

**DX-F1 (CRITICAL) — Gate 4 confirms BLIND.** Capture's gate verifies a URL/image the human
can SEE; motion's Gate 4 sets `confirmed:true` on JSON referencing a template + baked data +
lottie that renders nothing until AFTER confirmation + a full Docker render + re-stitch. The
gate's stated purpose (informed confirmation, monetization discipline) is unachievable. →
**ACCEPT FIX.** `yt-motion --init` (or `--preview`) renders a cheap per-item still/proof-frame
into `motion/previews/`; motion.json references the preview path so review-time and confirm-
time point at the same pixels. [P1 completeness] **Highest-value DX fix.**

**DX-F2 (CRITICAL) — Unguided hard-Docker onboarding on a machine that lacks Docker.** Prereqs
are documented + fail-fast, not checked + guided. Capture's only extra dep (Playwright) is
`pip`-trivial AND optional (degrades to press-kit). Motion has a HARD Docker dep (absent) with
no graceful floor — first run dies. → **ACCEPT FIX.** Add `yt-motion --doctor` preflight that
probes node/docker/HF and emits per-tool `next_action` with exact install commands + an
explicit "motion is optional; skip and keep b-roll" escape line. [P1, overlaps E-F5]

**DX-F3 (HIGH) — Error quality regresses from the repo's own bar.** Spec promises only "a clear
message"; `capture_sites.py` already practices typed `ERR_*` codes + `next_action` repair hints.
Motion's failure surface is LARGER (docker/node/HF missing, version mismatch, Chrome crash,
font missing, blank frame, alpha fail). → **ACCEPT FIX.** Define a `motion_*` ERR taxonomy
mirroring capture, each with problem + cause + `next_action`. [DX rule: errors always
problem+cause+fix]

**DX-F4 (HIGH) — Iteration tax: `--force` re-renders ALL comps.** Whole-stage `stage_done` means
fixing one bar-race re-pays every comp's Chrome render + a full re-stitch. → **ACCEPT FIX.**
Per-item hash (template+data+lottie+duration) skips unchanged comps even under `--force`; add
`--only <beat|comp>`. [P5 simpler loop, overlaps E-F6]

**DX-F5 (HIGH) — A failed override can break stitch's "every beat resolves" invariant.** Fail-
fast covers only prereqs, not mid-render. A `card`/`beat` override (which REPLACES the beat
asset) that crashes mid-render could leave the beat with NO asset, breaking `yt-stitch`'s
never-blank-beat floor (stitch SKILL line 16). Capture partial-succeeds + falls back to stock;
motion states no such floor. → **ACCEPT FIX.** Per-item try/skip with a `motion_render_failed`
warning; a failed `card`/`beat` falls back to the underlying stock b-roll so the beat still
resolves. State the partial-success contract in the SKILL. [P1 completeness]

**DX-F6 (MEDIUM) — Pin the slug-positional invocation.** Spec sometimes writes `yt-motion --init`
without the `<slug>` positional. → **ACCEPT FIX.** `motion_render.py <slug> --init` /
`<slug> [--force]` to byte-match capture. [P5]

### DX implementation checklist
- [ ] `--doctor` preflight (node/docker/HF) with install `next_action`s + skip-and-keep-b-roll escape
- [ ] `--init` renders per-item preview stills into `motion/previews/`; referenced in motion.json
- [ ] `motion_*` ERR taxonomy with `next_action`, reusing capture's envelope shape
- [ ] Per-item render hash + `--only <beat>`; success envelope prints "next: yt-stitch --force"
- [ ] Partial-success: failed `card`/`beat` → fall back to stock b-roll; warn, don't hard-fail
- [ ] `<slug>` positional mandatory, matching capture

## /autoplan — Cross-phase themes (flagged in 2+ phases independently)

- **Timing-fit (comp length vs beat duration)** — Design D-F5 + Eng E-F3b/E-F6. The
  single mechanical gap most certain to visibly break. High-confidence.
- **Unattended runtime / Docker-absent** — CEO + Eng E-F5 + DX DX-F2. Three phases. The
  plan's primary mitigation (Docker) isn't installed; nvm-node won't resolve non-interactive.
- **"Mirrors existing capture/PiP" is overstated** — Eng E-F3 (overlay compositor is new
  arch) + DX DX-F1/DX-F5 (inherits capture's SHAPE — gate, --init — but not its DX
  GUARANTEES: visible gate, graceful fallback, typed errors). The spec reuses vocabulary,
  not substance.
- **`lottie_gen.py` untracked + JSON-only** — CEO + Design D-F3. Must be productionized
  before any "reuse" claim holds; emits JSON, not video.

## /autoplan — Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale |
|---|-------|----------|----------------|-----------|-----------|
| 1 | CEO | Mode = SELECTIVE EXPANSION | Mechanical | P2 | Additive opt-in stage |
| 2 | CEO | Premise: motion-moves-retention | **User Challenge** | — | Both models said reframe; **operator chose B: keep HyperFrames** (has context models lack) |
| 3 | CEO | Alternatives table (B/C beat D) recorded | Mechanical | P1 | Spec skipped 0C-bis |
| 4 | Design | D-F1 commit hand-authored design system (not LLM-generated) | Mechanical | P1,P5 | channel.json has no visual tokens |
| 5 | Design | D-F2 commit motion tokens (ban bounce/elastic) | Mechanical | P1,P5 | "alive" undefined + off-brand risk |
| 6 | Design | D-F3 single style spec + owned Lottie set | Mechanical | P1 | tokens.css unifies color only |
| 7 | Design | D-F4 hook card: static drawtext vs subtle motion | **Taste** | P5 | Recommend static (legibility) |
| 8 | Design | D-F5 intro→elastic-hold→outro timing contract | Mechanical | P1 | Dead air / amputation |
| 9 | Design | D-F6 chart legibility spec + read-hold | Mechanical | P1 | Numbers channel, phone playback |
| 10 | Eng | E-F1 separate `overlay_layers()`, keep flat map | Mechanical | P4,P5 | Backward-compat with 5 tests |
| 11 | Eng | E-F2 precedence motion>capture + collision warn | **Taste** | P5 | Both human-confirmed; reasonable to flip |
| 12 | Eng | E-F3 post-concat alpha overlay (new arch) | Mechanical | P5,P1 | "mirrors PiP" is false |
| 13 | Eng | E-F3b alpha-preserving format, not `_norm` | Mechanical | P1 | yuv420p kills alpha |
| 14 | Eng | E-F4 add "motion" to manifest.STAGES + test | Mechanical | P5 | Stage never seeded |
| 15 | Eng | E-F5 preflight fail-fast (docker/node/HF) | Mechanical | P1 | Unattended PATH/daemon |
| 16 | Eng | E-F6 per-comp cache key + stitch invalidation | Mechanical | P1 | Re-render cost, stale timings |
| 17 | Eng | E-F7 test plan artifact (13 rows) | Mechanical | P1 | Spec had none |
| 18 | DX | DX-F1 per-item preview stills for Gate 4 | Mechanical | P1 | Confirms blind today |
| 19 | DX | DX-F2 `--doctor` preflight + skip-and-keep-b-roll | Mechanical | P1 | Docker absent, unguided |
| 20 | DX | DX-F3 `motion_*` ERR taxonomy + next_action | Mechanical | P1 | Regresses from capture |
| 21 | DX | DX-F4 per-item hash + `--only` | Mechanical | P5 | Iteration tax |
| 22 | DX | DX-F5 failed override → fall back to stock b-roll | Mechanical | P1 | Protects never-blank invariant |
| 23 | DX | DX-F6 mandatory `<slug>` positional | Mechanical | P5 | Match capture |

## Open follow-ups (out of scope for this spec)

- 9:16 Shorts variants of motion comps.
- `yt-script` emitting richer motion hints automatically.
- A catalog of reusable channel-branded chart templates beyond the first few.
