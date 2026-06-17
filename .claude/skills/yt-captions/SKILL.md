---
name: yt-captions
description: Generate styled, readable ASS captions for a video project from its voiceover.wav using WhisperX word-level timestamps and PySBD sentence segmentation. Use after yt-voice and before yt-stitch.
---

# yt-captions

Transcribes `audio/voiceover.wav` with WhisperX (CPU), aligns to word-level
timestamps, segments into readable sentence-bounded cues with PySBD (wrapped at a
max line width), and writes a styled ASS per aspect ratio.

## Run
`python .claude/skills/yt-captions/scripts/generate_captions.py <slug> [--force]`

## Notes
- **One ASS per aspect** (`captions_16x9.ass` at PlayRes 1920x1080,
  `captions_9x16.ass` at PlayRes 1080x1920), each with a font sized to its canvas.
  A single portrait ASS burned into a landscape video renders mis-sized, and
  16:9 long-form is the primary output. Stitch burns the matching file.
- Words are assigned to PySBD sentences by **character offset**, and blank /
  non-speech tokens are dropped — so contractions, numbers, and punctuation can't
  desync the cues or drop a spoken word.
- Output: a single JSON envelope on stdout AND `project/<slug>/.result.json`.

Idempotent: skips if stage `captions` is `done` unless `--force`.
