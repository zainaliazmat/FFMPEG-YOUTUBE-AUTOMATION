---
name: yt-stitch
description: Assemble the final video for a project with pure FFmpeg — timed b-roll with Ken Burns, title cards for the hook/outro, voiceover (with optional ducked music), and burned ASS captions. Renders 16:9 by default. Use as the final stage after voice, media, and captions are done.
---

# yt-stitch

Reads `manifest.json` (beat timings, assets, optional local music) plus the
per-aspect `captions_<aspect>.ass`, and renders `out/video_<aspect>.mp4` with pure
FFmpeg. 16:9 (1920x1080) is the default/primary output; pass `--aspect both` to also
render 9:16.

Per-beat assets are **reconciled** from `stages.media` (stock b-roll, the floor)
overlaid with `stages.capture` (product stills, which win for the beats they cover)
via `pipeline.assets.merge_assets`. Every body beat must resolve to an asset before
rendering; a missing one fails fast with the beat list, not deep inside ffmpeg.

## Run
`python .claude/skills/yt-stitch/scripts/stitch_video.py <slug> [--force] [--aspect 16x9|9x16|both]`

## How it renders correctly
- **Full timeline.** The video covers the entire voiceover (hook + every beat +
  outro). The hook and outro have no b-roll, so each gets a generated title card
  sized to its narration duration, with its text drawn on screen.
- **zoompan at target dimensions.** A stock still is fed as a single frame; `zoompan
  d=` fixes the output frame count exactly, rendered straight at the target WxH (no
  720p upscale blur).
- **Product stills are PiP, never full-bleed.** Any asset tagged `framing:"pip"`
  (captured by yt-capture) is rendered at ~72% on the branded card instead of a
  full-frame pan. This is the always-on *Bill Graham* reduced-size lever — the repo's
  only copyright-framing enforcement point. It applies ONLY to product stills; stock
  b-roll still fills the frame. See `RIGHTS.md`.
- **Voice is never dropped.** With music, the voice is `asplit` — one copy keys a
  `sidechaincompress` that ducks the music, the other is `amix`ed back in
  (`normalize=0`, so the voice stays at full level). With no music the voice is
  mapped directly.
- **Matched segments.** Every segment is normalized (`fps`, `format=yuv420p`,
  `setsar=1`) and forced to exactly its beat duration (`-t` + `tpad`/`trim`) before
  `concat`, so total video duration == audio duration.
- **Output:** `yuv420p`, `+faststart`. On ffmpeg failure the stderr tail is folded
  into the error envelope. Result is on stdout AND `project/<slug>/.result.json`.

Idempotent: skips if stage `stitch` is `done` unless `--force`.
