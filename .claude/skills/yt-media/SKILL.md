---
name: yt-media
description: Fetch royalty-free b-roll for a video project from Pexels and Pixabay, keyed off each script beat's b_roll_keywords. Use after script.json exists and before captions/stitch. Downloads assets locally and logs every license into manifest.json.
---

# yt-media

Fetches one b-roll asset per beat (Pexels primary, Pixabay fallback) into
`project/<slug>/media/`. Downloads locally (no hotlinking), caches by URL,
streams to disk with a size cap, backs off on HTTP 429, and logs source +
license into `manifest.json`.

## Run
`PEXELS_API_KEY=... PIXABAY_API_KEY=... python .claude/skills/yt-media/scripts/fetch_media.py <slug> [--force]`

## Notes
- The saved file extension comes from the API's **declared media type**
  (`video_files[].file_type`, Pixabay video = mp4, or the download
  Content-Type) — never from the URL string. Pexels video links are
  Vimeo-external URLs with a query string, so URL-suffix sniffing mislabels them.
- **No background-music fetch.** There is no public Pixabay music API. Background
  music is optional and comes from a local CC0 file dropped into a `music/`
  folder (YouTube Audio Library / Pixabay-downloaded); the first audio file there
  is used and logged. With no `music/` file, the video ships voice-only.
- Output: a single JSON envelope on stdout AND `project/<slug>/.result.json`.

Idempotent: skips if stage `media` is `done` unless `--force`.
