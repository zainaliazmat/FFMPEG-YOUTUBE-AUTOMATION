---
name: yt-voice
description: Generate voiceover audio from a video project's script.json using local Kokoro-82M TTS. Use when a project folder has a validated script.json and needs narration (audio/voiceover.wav) before media/captions/stitch stages.
---

# yt-voice

Generates `audio/voiceover.wav` for `project/<slug>/` from `script.json` using
Kokoro-82M (Apache-2.0, CPU). Synthesizes the hook + each beat narration + outro,
concatenates to one 24kHz WAV, and records per-segment `beat_timings` (hook = id 0,
outro = id -1, beats keep their real ids) into `manifest.json`.

## Run
`python .claude/skills/yt-voice/scripts/generate_voice.py <slug> [--force] [--voice NAME]`

- A single, consistent channel voice (`af_heart`) is locked in with a matching
  American `lang_code` (`a`). This is deliberate: a consistent voice is a
  monetization/authenticity best practice. `pick_voice()` is the seam where
  per-video rotation can be added later (keeping the accent prefix consistent
  with `lang_code`).
- Output: a single JSON envelope on stdout AND `project/<slug>/.result.json`.

Requires system `espeak-ng` and the project venv (`kokoro`, `soundfile`).
Idempotent: skips if stage `voice` is already `done` unless `--force`.
