# YouTube Video Generation Automation — Research Findings

> **Goal:** A fully-automated, 100% free/local Linux pipeline that discovers viral topics,
> writes high-retention scripts, generates voiceover (local TTS), sources royalty-free
> media + music, and stitches everything with FFmpeg into vertical Shorts (9:16) and
> long-form (16:9) videos. Each stage runs as a separate Claude Code skill.
>
> **Niche:** facts / educational / listicles.
> **Constraint:** free or local-only tooling, no paid services.
> **Research method:** deep-research harness — 106 agents, 24 sources, 105 claims
> extracted, 25 adversarially verified (2/3-vote), 23 confirmed, 2 refuted.
> **Date:** 2026-06-17

---

## TL;DR

A 100% free/local pipeline is feasible by chaining five core stages (+ captions), each as
its own Claude Code skill:

1. **Discover** — YouTube Data API v3 (`videos.list?chart=mostPopular`, 1 unit/call) + Reddit (PRAW). pytrends only as a fragile fallback.
2. **Script** — LLM-driven, hook-first, retention-structured.
3. **Voice** — **Kokoro-82M** (Apache 2.0, CPU-runnable, commercial-safe). Avoid F5-TTS/XTTS v2 (non-commercial licenses).
4. **Media** — **Pexels** (cleanest) + **Pixabay** (photos/video/music). Mind rate limits, caching, hotlinking rules.
5. **Captions** — WhisperX word-level timestamps + sentence segmentation (PySBD) for readable cues.
6. **Stitch** — FFmpeg: timed images + voiceover + ducked music + burned captions → 9:16 and 16:9.

Strongest-evidenced facts: API quotas, rate limits, and licensing. Weakest: TTS quality
rankings (secondary/blog benchmarks — treat exact numbers as indicative).

---

## 1. Topic Discovery `[confidence: HIGH]`

### YouTube Data API v3
- `videos.list` with `chart=mostPopular` returns most popular videos per region/category.
- **Cost: 1 quota unit/call.** Default quota: **10,000 units/day** (resets midnight Pacific) → thousands of free calls/day.
- `search.list` costs **100 units/call** (~100 searches/day) — use sparingly.
- ⚠️ **Caveat (2025-07-21):** YouTube deprecated its general Trending page; `chart=mostPopular`
  now surfaces only **Music / Movies / Gaming** charts — a **weak signal for an educational
  niche**. Combine with Reddit + category-filtered queries.

### Reddit (PRAW)
- `praw` = simple Python access to Reddit's API.
- Exposes ranked listings: `hot()`, `top()`, `new()`, and `reddit.front.hot()`.
- Best free idea-mining source for facts/educational content.
- Suggested subreddits: r/todayilearned, r/explainlikeimfive, r/Damnthatsinteresting,
  r/interestingasfuck, r/science, r/history.

### pytrends (Google Trends) — fallback only
- Unofficial, **archived 2025-04-17**, brittle, hits HTTP 429 on Google backend changes.
- Self-discloses: "not an official or supported API... Only good until Google changes their backend again."
- Official Google Trends API entered **limited alpha (July 2025)** — not yet a reliable free option.

**Sources:**
- https://developers.google.com/youtube/v3/docs/videos/list
- https://github.com/praw-dev/praw
- https://github.com/GeneralMills/pytrends
- https://www.getphyllo.com/post/youtube-api-limits-how-to-calculate-api-usage-cost-and-fix-exceeded-api-quota

---

## 2. Script Writing `[not verified — fill from domain knowledge]`

The research did not surface surviving verified claims on retention/hook frameworks. To be
built from domain knowledge. Working principles for the facts/listicle niche:

- **Hook in first 3 seconds** — open with the most surprising fact or a curiosity gap.
- **Retention structure** — open loop → payoff cadence; one idea per scene beat.
- **Scene beats** — script should emit discrete beats, each mapped to (a) a narration line
  and (b) 1–3 media search keywords for the media stage.
- **Pacing** — short sentences for TTS clarity; ~150 wpm narration target.
- Output a structured `script.json` (hook, beats[], outro, CTA) for downstream stages.

---

## 3. Local TTS `[confidence: MEDIUM on quality, HIGH on licensing]`

### Recommended default: Kokoro-82M
- **License: Apache 2.0 → commercial/monetization safe ✓**
- 82M params, runs on **CPU** or ~3GB GPU.
- ~**36× real-time** on a free Colab T4; **sub-0.3s** across 5–200 word inputs.
- Top-tier quality (hit #1 on TTS Arena blind naturalness).
- **Limitation:** ships fixed voicepacks only — **cannot clone voices.**

### Alternatives
| Model | License | Commercial? | Notes |
|---|---|---|---|
| **Kokoro-82M** | Apache 2.0 | ✅ Yes | Default. Fast, CPU-ok, no cloning. |
| **Piper** | MIT | ✅ Yes | Fastest GPU-free (~10× RT CPU, runs on Pi 5). |
| **Tortoise** | Apache 2.0 | ✅ Yes | Slower, high quality. |
| **Bark** | MIT | ✅ Yes | Expressive. |
| **StyleTTS 2** | MIT | ✅ Yes | High quality. |
| **F5-TTS** | CC-BY-NC-4.0 | ❌ **No** | Best naturalness + zero-shot cloning, but **non-commercial**. |
| **XTTS v2 (Coqui)** | Coqui Public Model License | ❌ **No** | Non-commercial; Coqui defunct Jan 2024. |
| **csm-1b (Sesame)** | unverified | ❓ | Top naturalness; license not confirmed — verify before use. |

### ⚠️ Licensing trap
F5-TTS and XTTS v2 sound the most natural but are **NOT licensed for monetized YouTube**.
This pushes **Kokoro (commercial-safe) to the front** as the pipeline default.

**Sources:**
- https://huggingface.co/hexgrad/Kokoro-82M
- https://www.inferless.com/learn/comparing-different-text-to-speech---tts--models-part-2
- https://ocdevel.com/blog/20250720-tts
- https://huggingface.co/SWivid/F5-TTS
- https://huggingface.co/coqui/XTTS-v2
- https://www.promptquorum.com/power-local-llm/local-tts-voice-cloning-piper-coqui-xtts

---

## 4. Free Stock Media + Music `[confidence: HIGH]`

### Pexels (cleanest for automation)
- Fully **free**, royalty-free photos AND videos.
- Rate limit: **200 req/hour + 20,000 req/month** (higher on request).
- Distinct endpoints: `/v1/search` (photos), `/v1/videos/search`, `/v1/collections`.
- No payment required.

### Pixabay (photos, video, AND music)
- Rate limit: **100 req / 60s**, tied to the **API key** (not IP).
- Honors `X-RateLimit-Limit/Remaining/Reset` headers; returns **HTTP 429** on overflow.
- **Must cache responses for 24 hours.**
- **Systematic mass downloads prohibited.**
- **No permanent hotlinking of images** — download to your server/disk first (videos may embed).
- **Source attribution required** when displaying search results.
- Royalty-free under the Pixabay Content License.

### Music
- Pixabay has a free music library.
- Other free sources: YouTube Audio Library, Free Music Archive, Incompetech (attribution).

### Pipeline implications
- Build **exponential backoff** on 429.
- Implement a **24h response cache** (required by Pixabay ToS).
- **Download media to local disk** before use (no hotlinking).
- Map each script scene beat → search keywords → fetch + cache.

**Sources:**
- https://www.pexels.com/api/documentation/
- https://pixabay.com/api/docs/
- https://scancode-licensedb.aboutcode.org/pixabay-content.html
- https://shotstack.io/learn/how-to-get-free-music-for-video-project-app/

---

## 5. Captions / Subtitles `[confidence: MEDIUM]`

- Use **WhisperX** for word-level timestamps from the generated voiceover.
- **Raw output makes ugly captions.** Readable SRT/ASS requires post-processing:
  1. Transcribe → word-level timestamps.
  2. **Segment into sentences** (e.g. **PySBD**; alternatives: srt_equalizer, whisper built-ins).
  3. Merge/split cues to respect **max line width** and **max line count**.
- WhisperX exposes `--max_line_width`, `--max_line_count`, `--segment_resolution`.
- ⚠️ **Refuted claim:** "WhisperX uses faster-whisper large-v3" was **refuted (1-2 vote)** —
  do not rely on that specific model detail.

**Sources:**
- https://github.com/dashed/whisperx-subtitles-replicate

---

## 6. FFmpeg Assembly `[not verified — fill from domain knowledge]`

No primary source in this research set covered the exact FFmpeg syntax. To be built:

- **Timed slideshow:** images with per-image durations (concat demuxer or `-loop`/`-t` per input),
  optional Ken Burns zoom (`zoompan`).
- **Audio ducking:** `sidechaincompress` filter — duck background music under the voiceover.
- **Burned captions:** `subtitles=captions.ass` (ASS preferred for styling) or `ass=` filter.
- **Two aspect ratios:**
  - Shorts: `scale`/`crop`/`pad` to **1080×1920 (9:16)**.
  - Long-form: **1920×1080 (16:9)**.
- Single source timeline → render twice with different scale/pad filters.

---

## Proposed Architecture — Chained Claude Code Skills

```
[1] /yt-discover   → topic ideas + scores        → topic.json
[2] /yt-script     → hook + script + scene beats  → script.json
[3] /yt-voice      → Kokoro TTS per scene         → audio/*.wav + timings
[4] /yt-media      → Pexels/Pixabay per scene     → media/*.jpg|mp4 + music
[5] /yt-captions   → WhisperX align + segment     → captions.ass
[6] /yt-stitch     → FFmpeg assemble + duck music → output_9x16.mp4 + output_16x9.mp4
```

**Chaining model**
- Shared `project/<slug>/` folder per video, with a `manifest.json` as the single source of truth.
- Each skill is **independently runnable and idempotent** (re-run media without redoing TTS).
- A top-level `/yt-make` orchestrator runs stages in sequence.
- **Python does the heavy lifting** (APIs, Kokoro, WhisperX, FFmpeg); skills are the
  orchestration + LLM-reasoning layer (topic selection, script writing, scene→keyword mapping).

**Stack (all free)**
- Python venv: `kokoro`, `praw`, `google-api-python-client`, `whisperx`, `requests`
- System: FFmpeg
- API keys needed: YouTube Data API (Google Cloud), Reddit app (PRAW), Pexels, Pixabay

---

## Open Questions / Next Steps

1. **FFmpeg specifics** — exact commands for timed images + ducking (`sidechaincompress`) +
   burned captions for both aspect ratios. *(Build & test locally.)*
2. **Trending substitute** — given `mostPopular` narrowing, best free general-trend signal for
   educational niche (Reddit + YouTube category queries + autocomplete scraping?).
3. **Script frameworks** — concrete retention/hook prompts for the facts/listicle niche.
4. **csm-1b license** — verify before considering as a quality alternative to F5-TTS.
5. **API keys** — confirm which keys are already available vs. need to be created.

---

## Refuted Claims (do NOT rely on)

- ❌ "WhisperX uses faster-whisper large-v3 for word-level timestamps" — vote 1-2.
- ❌ "Kokoro-82M placed in mid-tier (Tier 2.5) rather than top open-source tier" — vote 0-3
  (Kokoro is top-tier, this ranking was rejected).

---

## All Sources

**Primary:**
- https://developers.google.com/youtube/v3/docs/videos/list
- https://github.com/praw-dev/praw
- https://github.com/GeneralMills/pytrends
- https://www.pexels.com/api/documentation/
- https://pixabay.com/api/docs/
- https://huggingface.co/hexgrad/Kokoro-82M
- https://huggingface.co/SWivid/F5-TTS
- https://huggingface.co/coqui/XTTS-v2

**Secondary / Blog:**
- https://www.getphyllo.com/post/youtube-api-limits-how-to-calculate-api-usage-cost-and-fix-exceeded-api-quota
- https://www.inferless.com/learn/comparing-different-text-to-speech---tts--models-part-2
- https://ocdevel.com/blog/20250720-tts
- https://www.promptquorum.com/power-local-llm/local-tts-voice-cloning-piper-coqui-xtts
- https://portalzine.de/text-to-speech-solutions-ranked-by-speech-quality/
- https://github.com/dashed/whisperx-subtitles-replicate
- https://shotstack.io/learn/how-to-get-free-music-for-video-project-app/
- https://awakenerd.com/2024/03/21/create-a-slideshow-with-ffmpeg/
- https://www.ffmpeg-micro.com/blog/ffmpeg-create-slideshow-from-images
