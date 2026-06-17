# Faceless YouTube Pipeline — Spine v1 (Design)

**Date:** 2026-06-18
**Status:** Approved (design)
**Author:** synthesized from `compass_artifact_...md` + `RESEARCH.md`

## Goal

A 100% free / local Linux pipeline that turns **one hand-authored `script.json`**
into a watchable, captioned video in **both 9:16 (Shorts) and 16:9 (long-form)**,
running entirely on CPU. No paid services.

This spec covers **v1: the render spine (stages 3–6)**. Topic discovery (stage 1)
and automated script writing (stage 2) are explicitly deferred to a follow-up spec;
the data contract here is designed to accept them with no rework.

**Niche:** facts / educational / listicles.

## Source-of-truth decisions (why this synthesis)

The two research documents agree on the core stack. Where they differ, this design picks:

| Dimension | Decision | Source / reason |
|---|---|---|
| Architecture | 6 single-responsibility Claude skills, JSON handoff via on-disk folder | Both agree |
| TTS | **Kokoro-82M** (Apache-2.0, single preset voice, 24 kHz) | Both agree; commercial-safe |
| Avoid | F5-TTS (CC-BY-NC), XTTS-v2 (CPML, Coqui defunct) | Both agree — demonetization risk |
| Media | Pexels (primary) + Pixabay (fallback + music) | Both agree |
| Media ToS | download local (no hotlinking), 24h cache, exp-backoff on 429, log license | RESEARCH.md (more precise) |
| Captions | WhisperX word timestamps **+ PySBD** sentence segmentation → styled ASS | Merge: RESEARCH's PySBD + Compass styling |
| **Assembly** | **Pure FFmpeg** (zoompan, sidechaincompress, ASS), not MoviePy | RESEARCH.md — far faster on CPU-only |
| **Output** | **Both** 9:16 and 16:9 (one timeline, two render passes) | RESEARCH.md explicit goal |
| Script/hook frameworks (future stage 2) | Compass's 6-part structure + hook categories + median-of-10 outlier scoring | Compass is the evidence-rich source |
| Approval gate | One human gate on `script.json` before any rendering | Compass recommendation |

## Environment (verified 2026-06-18)

- Linux, Python 3.12.3, ffmpeg 6.1.1 present.
- **CPU-only** (no GPU), 31 GB RAM, 4 cores → pure FFmpeg + Kokoro CPU mode.
- `espeak-ng` **not installed** — required by Kokoro (`apt install espeak-ng`).

## Architecture

Each skill is a `.claude/skills/<name>/` folder with `SKILL.md` (≤500 lines) plus
`scripts/*.py`. Claude orchestrates; **skills never call each other** — they read/write
a per-video project folder. Every script returns `{"success": bool, "error": ...}` and
is **idempotent** (re-run media without redoing TTS).

### Per-video folder contract

```
project/<slug>/
  manifest.json          # single source of truth: stage status, paths, license log
  script.json            # INPUT (hand-authored in v1)
  audio/voiceover.wav    # stage 3 (Kokoro)
  audio/music.mp3        # stage 4 (Pixabay CC0 music)
  media/*.jpg|*.mp4      # stage 4 (downloaded local)
  captions.ass           # stage 5 (WhisperX + PySBD)
  out/video_9x16.mp4     # stage 6
  out/video_16x9.mp4     # stage 6
```

### script.json schema (v1 input)

```json
{
  "slug": "string",
  "title": "string",
  "hook": "string (narration for first 3s)",
  "beats": [
    {
      "id": 1,
      "narration": "string — one idea, short sentences for TTS",
      "on_screen_text": "string (optional)",
      "b_roll_keywords": ["kw1", "kw2"]
    }
  ],
  "outro": "string",
  "cta": "string"
}
```

### manifest.json schema

```json
{
  "slug": "string",
  "created": "ISO-8601",
  "stages": {
    "voice":    {"status": "pending|done|error", "artifact": "audio/voiceover.wav", "beat_timings": []},
    "media":    {"status": "...", "assets": [{"beat": 1, "path": "media/...", "source": "pexels", "license": "..."}]},
    "music":    {"status": "...", "path": "audio/music.mp3", "source": "pixabay", "license": "CC0"},
    "captions": {"status": "...", "artifact": "captions.ass"},
    "stitch":   {"status": "...", "outputs": ["out/video_9x16.mp4", "out/video_16x9.mp4"]}
  }
}
```

## Skills (v1)

### 1. `yt-voice`
- Reads `script.json`, runs Kokoro-82M per beat (preset voice, e.g. `af_heart`), 24 kHz.
- Concatenates beats into `audio/voiceover.wav`; records per-beat start/end timings into manifest.
- Deps: `kokoro`, `soundfile`, system `espeak-ng`.

### 2. `yt-media`
- For each beat's `b_roll_keywords`: query Pexels `/v1/videos/search` then `/v1/search`
  (photos); fall back to Pixabay. Prefer video, else image.
- Download assets to `media/` (no hotlinking). 24h response cache. Exponential backoff on HTTP 429.
- Fetch one Pixabay CC0 music track → `audio/music.mp3`.
- Log every asset's source + license into `manifest.json`. **Pixabay/Pexels only.**
- Deps: `requests`.

### 3. `yt-captions`
- WhisperX transcribe `voiceover.wav` → word-level timestamps.
- PySBD sentence segmentation; merge/split cues to respect max line width + line count.
- Emit styled `captions.ass` (centered, bold, large, white + stroke; phrase highlighting).
- Deps: `whisperx`, `pysbd`.

### 4. `yt-stitch`
- Pure FFmpeg. Build timeline: each beat's media shown for its beat duration, with
  `zoompan` Ken Burns on stills.
- Mix audio: voiceover + music ducked via `sidechaincompress`.
- Burn `captions.ass` via `ass=` filter. `yuv420p`, `+faststart`.
- Render **twice**: 1080×1920 (scale/crop/pad 9:16) and 1920×1080 (16:9).
- Deps: system `ffmpeg`.

### Orchestrator `/yt-make`
- Thin slash/skill that runs voice → media → captions → stitch in order, checking each
  stage's `success` and manifest status before proceeding.
- **Approval gate:** surfaces `script.json` for human OK before any rendering begins.
  (When stage 2 lands, the gate sits naturally right after script generation.)

## Error handling

- Every script returns `{"success": bool, "error": str|null, ...}` instead of throwing,
  so the orchestrator can route/retry.
- Network stages (media/music) implement exponential backoff on 429 and a 24h cache.
- Idempotency: a stage with `status: done` in the manifest is skipped unless `--force`.

## Testing

- **Unit-ish:** each script runnable standalone against a 2-beat fixture `script.json`.
- **Smoke:** fixture → voice → media → captions → stitch; assert:
  - both MP4s exist and are non-zero,
  - each has one audio + one video stream (ffprobe),
  - duration ≈ total narration length (±1s),
  - every fetched asset has a license entry in `manifest.json`.
- Media tests use a small recorded/cached fixture response to avoid live API flakiness in CI.

## Out of scope for v1 (next spec)

- `yt-discover`: Reddit-primary (PRAW) + YouTube category queries + median-of-last-10
  outlier scoring (`mostPopular` is deprecated to Music/Movies/Gaming since 2025-07;
  pytrends archived 2025-04 → fallback only).
- `yt-script`: Compass 6-part structure (Hook → Context → core segments → re-hook → CTA),
  ~150 wpm pacing, 3–5 hook variants.

## Open items to resolve during implementation

- Install `espeak-ng` and pin Python deps in `requirements.txt` (Kokoro, whisperx, pysbd, requests).
- Confirm which API keys exist vs. need creating (Pexels, Pixabay; YouTube/Reddit for next spec).
- Decide beat-duration source: derive from Kokoro per-beat audio length (preferred) vs. fixed.
