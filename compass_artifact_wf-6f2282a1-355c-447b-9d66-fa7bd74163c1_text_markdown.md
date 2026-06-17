# Building a Fully-Automated, Near-Free Faceless YouTube Pipeline Orchestrated by Claude Skills

## TL;DR
- **It is buildable today for ~$0 in recurring software cost**: the best free stack is YouTube Data API v3 + pytrends + Reddit/PRAW for ideation, Claude itself for scripts/hooks, **Kokoro-82M** for TTS, **Pexels + Pixabay** for visuals, **Pixabay Music / YouTube Audio Library** for audio, **faster-whisper/WhisperX** for caption timing, and **MoviePy + ffmpeg** for assembly — all glued together by a set of single-purpose Claude Agent Skills that pass data via JSON files on disk.
- **Architect it as 6–8 small skills, not one mega-skill**, each a folder with a SKILL.md (under 500 lines) plus Python scripts run via bash; Claude acts as the orchestrator reading/writing a shared `project.json` state file between stages.
- **The two licensing traps that can demonetize a channel** are TTS commercial-use terms (use Apache-2.0 Kokoro; avoid Coqui XTTS-v2, whose CPML commercial license is no longer obtainable since Coqui shut down in January 2024, and F5-TTS, which is CC-BY-NC-4.0 and prohibits commercial use without a separate agreement) and music Content ID (use Pixabay Music or the YouTube Audio Library, never "royalty-free" tracks of unknown registration).

## Key Findings

1. **Free tooling is now good enough end-to-end.** Open-source TTS reached rough parity with paid services in 2025–2026, free stock APIs (Pexels/Pixabay) grant commercial use with no attribution, and Whisper variants give frame-accurate captions for free. The only unavoidable cost is electricity/GPU time and a Claude subscription you already have.
2. **Kokoro-82M is the recommended TTS** for faceless narration: Apache-2.0 (full commercial use), runs on CPU or <2GB VRAM, 36–96× real-time on GPU, and is the top-ranked *browser-runnable / consumer-hardware* model on TTS Arena (see caveat — on the full Artificial Analysis TTS Arena it sits ~32nd of 74 at Elo ~1056; its "#1" status is among models you can actually self-host for free). Its one limitation — no voice cloning — does not matter for faceless content using a consistent preset voice.
3. **Claude Skills map cleanly onto pipeline stages.** Anthropic's own guidance (progressive disclosure, single responsibility, scripts-as-tools) is a near-perfect fit for a deterministic media pipeline where each stage emits structured JSON.
4. **Outlier detection is the core of virality scoring** and can be reproduced free with the YouTube Data API v3: compare a video's views against the median of a channel's last ~10 uploads.
5. **Content ID is a real, large-scale monetization risk.** Per YouTube's Copyright Transparency Report (reported via TorrentFreak, June 2026), the platform processed **2,502,941,368 Content ID claims in 2025** (≈2.5 billion, up 14% from 2.2 billion in 2024); over 99% of claims are automated and rightsholders chose to monetize over 90% of them — meaning an unsafe music track silently redirects your ad revenue rather than just getting flagged.

## Details

### Stage 1 — Viral Topic Research / Ideation

**Free data sources:**
- **YouTube Data API v3** — free, 10,000 quota units/day, no credit card. Per Google's Quota Calculator the default allocation works out to about **100 `search.list` calls per day** (each costs 100 units), while `videos.list` and `channels.list` cost 1 unit each (batch up to 50 IDs). Efficient pattern: enumerate a channel's uploads via `playlistItems.list` (1 unit), then batch `videos.list` for statistics. Public stats lag minutes-to-hours; quota resets midnight Pacific.
- **Google Trends via pytrends** — unofficial free Python wrapper. Supports `trending_searches()`, `realtime_trending_searches()`, `interest_over_time()`, related queries. Rate-limited; sleep ~60s between calls when throttled. Google launched an official alpha Trends API in 2025 (limited quota). Note pytrends returns sampled data and can include zero-replacement noise.
- **Reddit API (PRAW)** — free; `/r/{sub}/hot`, `/top`, `/new`, 100 posts/call, ~1,000-post ceiling. You can append `.json` to nearly any Reddit URL for free (e.g. `reddit.com/r/popular/top.json`).
- **TikTok trending** — no free official API; TikTok Creative Center is the data source. Open-source **Trendgetter** (MIT, github.com/Zivsteve/trendgetter) aggregates Google/YouTube/X/Reddit/GitHub/TikTok trends into one self-hostable API.
- **VidIQ/TubeBuddy free tiers** exist but are UI tools, not bulk APIs; useful for manual validation only.

**Virality scoring (the outlier method):** The industry-standard metric is an outlier multiplier = video views ÷ the channel's baseline views. The most precise published definition (from SocialNorn and confirmed by MrBeast's Viewstats tool, which states a "204x outlier score… means this video has 204 TIMES more views than the last 10 videos averaged at that time") divides view count by the **median of the channel's last 10 uploads** — median preferred over mean because it resists skew from prior hits, and over subscriber count which is a poor baseline. Tools like vidIQ, 1of10, Viewstats and OutlierKit all use this concept; common thresholds: **3x+ is meaningful, 5x+ strong, 10x+ viral** (OutlierKit: "Most pros focus on 3x+ outliers. 2x might be noise, but 3x+ consistently indicates something worked"). A composite virality score combines:
- outlier multiplier (~45% weight, dominant signal)
- velocity = views ÷ days since publish, or views-per-hour for momentum (~25%)
- engagement = (likes + comments) / views, healthy range ~1–5% (~15%)
- topic search demand (~15%), approximated by how many independent channels show outliers on the same topic since the free API has no search volume.

Note: the exact formulas of vidIQ and OutlierKit are proprietary; the median-of-last-10 formula is the best-supported concrete parameterization.

**Open-source references:** `patrickloeber/youtube-analyzer` (Python `YTstats` class pulling channel video stats) is the best starting point to build the multiplier yourself; n8n workflow #2903 ("YouTube outlier detector") is the closest free turnkey implementation. No fully free end-to-end "virality scorer" repo exists — you assemble it.

### Stage 2 — Script Writing (Claude prompt engineering)

Since the user is on Claude, scripts should be generated by Claude itself with strong structural prompting rather than a third-party tool. Evidence-based structure:
- **6-part structure**: Hook (0–30s) → Context Bridge (30–90s) → 3–5 Core Value Segments (each with its own setup/development/payoff) → Pattern Interrupts every 30–45s → Mid-video re-hook at 40–60% → CTA.
- **Pacing**: natural narration ≈ 130 words/minute (some sources cite 130–160). A 10-minute video ≈ 1,300 words. Allocate ~200 words per core section; mark word counts per section to prevent ballooning and to give the LLM a hard constraint.
- **Retention claims from creator analytics**: scripted videos average 40–60% retention vs 25–35% unscripted; a pattern interrupt every ~90s can lift average view duration 15–25%; the dopamine/curiosity-loop principle (open a loop, resolve it, open a new one) drives retention.
- **Listicle/Top-10 specifics**: build momentum from the last item to #1, each item a mini-segment with its own setup and payoff; tease the #1 spot in the hook to keep viewers to the end.
- **Best practice**: write the hook LAST (after the body exists), keep hook sentences under ~10 words, and define a single "core promise" sentence that every section must serve (kills topic drift, the #1 failure mode of AI scripts).
- Free specialized references exist (FacelessOS skill files built from 7,000+ scripts; Subscribr's WHY-WHAT-HOW / OBSERVATION-INSIGHT-EVIDENCE templates) but a well-prompted Claude skill replicates these.

A useful Claude prompt pattern: have the script skill emit **structured JSON** — an array of scenes, each with `narration`, `on_screen_text`, `b_roll_keywords`, and `is_pattern_interrupt` — so downstream media/caption skills can consume it directly.

### Stage 3 — Viral Hooks

The first 10–30 seconds determine distribution; the steepest drop-off is 0:00–0:15. The informal (non-official) benchmark: 70%+ retention at 30s pushes a video into Suggested; below 60% it stalls. Psychological principles: **curiosity gap** (the brain seeks closure on incomplete info), **open loops**, **pattern interrupt** (novelty/contrast resets attention), **FOMO**, **social proof**. Proven hook categories: bold/counterintuitive claim, curiosity gap, result-first (show the payoff immediately), direct question, micro-story, visual shock. For faceless channels (no personal brand to lean on), **bold claims and curiosity gaps drive the fastest early retention**. Mistakes to avoid: animated intros (a 3-second logo reportedly costs 8–15% of viewers), "Hey guys welcome back," restating the title, slow zoom with no audio (the algorithm reads early inaction negatively).

**Generation/testing approach**: have Claude produce 3–5 hook variants per script (the hook-generator skill), then A/B test by publishing variants and comparing 3-second and 30-second retention in YouTube Studio's Audience Retention report. Maintain a "swipe file" of hooks that stopped your own scroll, since top creators remix proven patterns rather than inventing new ones.

### Stage 4 — Text-to-Speech (deep comparison)

**Kokoro-82M (RECOMMENDED).** 82M params, modified StyleTTS2 architecture, **Apache-2.0** (full commercial/monetized use), v1.0 released Jan 27, 2025, shipping **54 voices across 8 languages**. Runs on CPU or <2GB VRAM (even a 2016 GTX 1060); 36–96× real-time on GPU, 3–11× on CPU. Trained only on permissive/non-copyrighted audio. **No voice cloning** (preset voices only) — irrelevant for faceless work with a consistent narrator. Python: `pip install kokoro soundfile` + `espeak-ng`; `KPipeline(lang_code='a')`, voices like `af_heart`, `am_adam`, `bf_emma`; outputs 24kHz. A community Docker image (`ghcr.io/remsky/kokoro-fastapi-gpu`) exposes an OpenAI-compatible API for zero-config integration.

**Comparison of other free/open options:**
- **Piper** (MIT core code; note the active fork OHF-Voice/piper1-gpl is GPL, and the espeak-ng phonemizer is GPL) — CPU-only, 50+ languages, fast even on a Raspberry Pi; quality "good but clearly synthetic," no cloning. Best for extreme low-power or many-language needs. Voice-model licenses vary (many CC-BY-4.0; avoid Blizzard-licensed derivatives for commercial use).
- **Coqui XTTS-v2** — gold-standard zero-shot cloning (6s reference, 17 languages), 4–6GB VRAM, **but the CPML license now effectively bars commercial use**: Coqui shut down in January 2024 and, per the project's own GitHub discussion, "there is no one to sell a commercial license anymore." **Avoid for monetized content.**
- **F5-TTS** — flow-matching, 3s cloning, fast; **CC-BY-NC-4.0 — commercial use prohibited without a separate agreement. Avoid for monetization.**
- **Chatterbox / Chatterbox-Turbo** (Resemble AI, MIT) — best free voice cloning (10s reference, ~6GB), Turbo is one-step/fast. Use if you need a cloned voice on a gaming GPU.
- **Qwen3-TTS** (Apache-2.0) — clones from 3s, lowest WER among open models; best permissively-licensed cloning choice if you have a GPU.
- **Fish Speech / OpenAudio S1 / Fish Audio S2** — top quality + 80+ languages, but **weights are research/non-commercial; commercial use needs a paid license**; 12–16GB+ VRAM to self-host.
- **StyleTTS2** (MIT) — near-human English MOS, 2–4GB VRAM.
- **Dia 1.6B** (Apache-2.0) — multi-speaker dialogue with nonverbal tags, ~10GB VRAM, English-only.
- **MeloTTS / Parler-TTS** (Apache-2.0) — fully commercial, solid baselines.
- **VibeVoice** — long-form multi-speaker podcast-style.

**Verdict:** Kokoro for narration (free, commercial-safe, runs anywhere). If you later need a signature cloned voice, use Chatterbox or Qwen3-TTS (both permissively licensed). Specifically avoid XTTS-v2 and F5-TTS for monetized channels.

### Stage 5 — Stock Images / B-roll Video

- **Pexels API (RECOMMENDED primary)** — completely free. Per the Pexels Help Center: "By default, the API is rate-limited to **200 requests per hour and 20,000 requests per month**… If you meet our API terms, you can get unlimited requests for free." Pexels License: free for commercial use, **no attribution required** (a link back to Pexels is requested for API apps). Photos + videos (~150k videos). Caveat: **no indemnification** — you bear copyright risk; content can't be resold unmodified.
- **Pixabay API** — free, ~100 requests/minute, images + videos + **music**. Pixabay License allows commercial use, no attribution, but **requires a "Pixabay" source mention in apps and prohibits permanent hotlinking** (download to your server first). Best when you want to self-host assets.
- **Unsplash API** — photos only (no video), free, but API terms require attribution and hotlinking the returned URLs — less flexible for a render pipeline.
- **Others**: Coverr (free API, video, requires logo credit), Mixkit, Wikimedia Commons (per-file license checks).

**Matching clips to script:** use the per-scene `b_roll_keywords` array from the script JSON, then query Pexels/Pixabay per scene. For better matching, embed scene text and asset metadata and rank by cosine similarity. Download (don't hotlink) to a local `assets/` folder.

**Free AI image generation (optional):** **Pollinations** (open-source, Berlin) — dead-simple URL/HTTP API (`image.pollinations.ai/prompt/{text}?model=flux`), Flux/GPT-Image/Seedream, no key for basic use (anonymous: 1 req/15s; free "Seed" tier 1 req/5s; free-tier images may carry watermarks since March 2025 unless registered). For local generation: **Flux** and **Stable Diffusion/SDXL** via ComfyUI; **Z-Image-Turbo** and **Qwen-Image** are Apache-2.0 and commercial-friendly. Verify per-model license for monetized use.

### Stage 6 — Background Music / Audio

The danger is **Content ID**: "royalty-free" ≠ "Content ID-free." With ~2.5 billion claims processed in 2025, >99% automated, and rightsholders monetizing over 90% of them, an unsafe track silently diverts your ad revenue.
- **YouTube Audio Library (SAFEST)** — inside YouTube Studio, pre-cleared for monetization, whitelisted from Content ID. No public API (access via Studio, so this stage may need a manual or browser-automation step).
- **Pixabay Music (RECOMMENDED for automation)** — ~30,000 tracks, CC0-style Pixabay License, no attribution, commercial-safe, accessible via the same Pixabay API as images/video. Still spot-check tracks for registered signatures.
- **Free Music Archive (FMA)** — ~150k–180k tracks, **per-track CC license must be checked** (CC0/CC-BY ok for commercial; CC-BY-SA/CC-BY-NC not). Has an API.
- **Jamendo API** — free tier for the CC catalog, but **commercial/broadcast use requires a paid per-track Jamendo Licensing deal**; the free side is non-commercial only. Use cautiously.
- **NCS** (credit required), Mixkit, Incompetech (CC-BY).

**Safety rule for the music skill**: only pull from Pixabay Music (CC0) or the YouTube Audio Library; log each track's license into `project.json`; before publishing, search "track title + Content ID" as a final check.

### Stage 7 — Video Stitching / Assembly

- **MoviePy** (MIT, v2.x current; note v2 introduced breaking changes vs v1) — Pythonic editing on top of ffmpeg/NumPy; ideal for composing image+audio+caption clips, Ken Burns/zoom-pan (animated resize/position over clip duration), crossfades, `TextClip` captions. Slower than raw ffmpeg but flexible. A 4–6 minute video can take ~30–40 min to render with 4 threads (per the real implementation `SiddheshKanawade/voxtale`).
- **ffmpeg / ffmpeg-python** — call directly for fast concatenation, encoding, burning subtitles (`-vf subtitles=`), and the final mux; much faster and more memory-efficient than MoviePy for plain conversions. Use `yuv420p` pixel format and `+faststart` for broad player compatibility (this also prevents the 0x80004005 corruption error on Windows).
- **Timing images to voiceover**: generate the narration first, then get word/segment timestamps. Use **WhisperX** (built on faster-whisper; VAD + wav2vec2 forced alignment → sub-100ms word timestamps, 60–70× real-time batched; BSD-2; needs a HuggingFace token only for diarization, which you don't need) or **whisper-timestamped** or plain **faster-whisper**. Word-level timestamps let you (a) cut images/scenes on segment boundaries and (b) burn animated word-by-word ("karaoke") captions (WhisperX's `--highlight_words`). Caveat: WhisperX alignment can be less precise than the Montreal Forced Aligner for some words, but is far easier and fast enough for captions.
- **Captions**: transcribe the TTS audio with Whisper → SRT/JSON → render styled `TextClip`s in MoviePy or burn via ffmpeg. Common high-retention style: centered, bold, large, white with stroke, one-word or short-phrase highlighting.
- **Ken Burns**: apply a slow zoom/pan to each still by animating its scale/position over the clip duration in MoviePy.

### Stage 8 — Orchestration & Claude Skills Architecture

**What a Skill is:** a directory with a `SKILL.md` (YAML frontmatter `name` + `description`, then Markdown instructions) plus optional `scripts/`, `references/`, `assets/`. Only `name` + `description` are pre-loaded into context at startup (Level 1 of progressive disclosure); the SKILL.md body loads when triggered (Level 2); bundled files/scripts load only when read or executed (Level 3). Scripts run via bash without loading their source into context (only their output consumes tokens), which makes them far more efficient than having Claude generate equivalent code on the fly.

**Anthropic best practices (apply directly):**
- Keep SKILL.md **under 500 lines**; split overflow into `references/` linked one level deep.
- The **description is the trigger** — include both what it does and *when to use it*; this is how Claude selects among many skills.
- **One skill = one responsibility**; split when contexts are mutually exclusive or rarely used together.
- Standard layout: `scripts/` (tiny single-purpose CLIs), `references/` (schemas/cheatsheets), `assets/` (templates). Use relative paths with forward slashes. Don't bundle library code or README/CHANGELOG files (they're for the agent, not humans).
- Make explicit whether Claude should *run* a script or *read* it as reference.
- Use Skills only from trusted sources (ones you authored) — they can execute code.

**Recommended skill decomposition (6–8 skills):**
1. `topic-research` — runs YouTube API + pytrends + Reddit scripts, scores outliers, writes `topics.json`.
2. `script-writer` — Claude generates the structured script (with per-scene `b_roll_keywords`) into `script.json`; mostly instructions, little code.
3. `hook-generator` — produces/ranks 3–5 hook variants into `hooks.json` (can be merged into script-writer).
4. `tts-narration` — runs `kokoro_tts.py` over `script.json` → `audio/voiceover.wav`.
5. `caption-align` — runs `whisperx_align.py` → `captions.json`/`.srt` with word timestamps.
6. `media-fetch` — runs `pexels_pixabay.py` per scene keywords → `assets/` + `assets.json`.
7. `music-fetch` — pulls a Pixabay/YT-Audio-Library track → `audio/music.mp3` + license log.
8. `video-assemble` — runs `moviepy_build.py` consuming all the above → `output.mp4`.

**Passing data between stages:** Claude is the orchestrator; **skills don't call each other directly** — Claude reads one skill's output and decides the next call. Use a shared on-disk state file (`project.json`) plus stage artifacts in a fixed dated project folder. Each script reads inputs from known paths and writes structured JSON with consistent field names; every script should **return a `{"success": bool, "error": ...}` object rather than throwing**, so Claude can check the result and route/retry. Define the JSON schema/contract for each stage *before* implementing. Hardcode output paths so artifacts are reproducible. For unattended runs, trigger Claude Code via cron/Task Scheduler (Claude has no built-in scheduler); a parent "orchestrator" skill or slash command runs the stages in sequence, and PostToolUse hooks can chain steps. Keep a **human-in-the-loop approval gate after script/hook generation** — this is the one place creative judgment most affects performance and protects against AI "slop."

**Reproducibility**: commit the skills folder to git; pin Python deps in `requirements.txt`; store all run artifacts under a dated project directory; log every API call and license decision into `project.json`.

### Reference open-source projects to study
- **SaarD00/AI-Youtube-Shorts-Generator** — full faceless factory: Gemini script (Hook→Context→Mechanism→Twist), Bark TTS, Pexels dual-visual A/B split, ffmpeg composer. Clean `modules/` separation (brain/audio/asset_manager/composer) — an excellent template for your skill decomposition.
- **Dark2C/Viral-Faceless-Shorts-Generator** — containerized: Google Trends → Gemini script → Piper TTS → Aeneas forced alignment → ffmpeg; one-click web trigger UI.
- **SamurAIGPT/AI-Youtube-Shorts-Generator** — long→short clipping with Whisper + LLM highlight ranking; CLI + Python library, JSON output for downstream automation; local mode uses yt-dlp + faster-whisper + ffmpeg/opencv.
- **Automated Video Generator** (MIT) — Remotion + Edge-TTS + stock APIs + batch render + MCP support.
- **IgorShadurin/app.yumcut.com** — Next.js end-to-end short generator, FFmpeg-ready, local-first.
- **pollinations/pollinations** — free Gen-AI image/text API to integrate.

## Recommendations

**Recommended best free stack (start here):**

| Stage | Pick | Why |
|---|---|---|
| Ideation | YouTube Data API v3 + pytrends + PRAW | Free, scriptable; build outlier scorer on `patrickloeber/youtube-analyzer` |
| Script | Claude skill (6-part structure) | You already pay for Claude; no extra tool |
| Hooks | Claude skill (3–5 variants) | Same |
| TTS | **Kokoro-82M** | Apache-2.0, CPU-capable, free, top consumer-hardware model |
| Visuals | **Pexels** (primary) + **Pixabay** (fallback/self-host) | Commercial, no attribution |
| AI images (optional) | Pollinations / local Flux/SDXL | Free; check model license |
| Music | **Pixabay Music** or **YouTube Audio Library** | CC0/whitelisted, Content-ID-safe |
| Caption timing | **faster-whisper / WhisperX** | Free, word-level, fast |
| Assembly | **MoviePy + ffmpeg** | MIT, flexible + fast mux |
| Orchestration | **Claude Agent Skills** (6–8) + cron | Progressive disclosure, JSON handoffs |

**Staged build plan:**
1. **Week 1 — Prove the spine.** Hardcode one topic; build `tts-narration` (Kokoro) → `caption-align` (WhisperX) → `video-assemble` (MoviePy) over a folder of manually picked Pexels clips. Goal: one watchable MP4 end-to-end.
2. **Week 2 — Automate inputs.** Add `script-writer`/`hook-generator` skills and `media-fetch` keyed off per-scene keywords; add `music-fetch` from Pixabay.
3. **Week 3 — Add ideation + orchestration.** Build the `topic-research` outlier scorer; write the orchestrator skill + `project.json` contract; add the human approval gate after script.
4. **Week 4 — Harden.** Add error objects/retries, cron scheduling, git versioning, and a pre-publish Content ID + license check.

**Thresholds that change the plan:**
- If CPU TTS render time bottlenecks throughput, add a cheap GPU (Kokoro hits 36×+ real-time) — switch only when batch render time exceeds your daily cadence.
- If a single Pexels key's 20k/month cap binds, request unlimited (free, if you meet API terms) or add Pixabay as a second source.
- If you need a distinctive branded voice, only then move from Kokoro to Chatterbox/Qwen3-TTS (keep licensing permissive).
- If outlier scoring needs the search-volume signal the free API lacks, layer in Google Trends rather than paying for OutlierKit/vidIQ.
- If you cross the YouTube Partner Program threshold, prioritize the Content ID / licensing audit before scaling upload volume.

## Caveats
- **Licensing is the highest-stakes risk.** Confirm each TTS model and music track's commercial terms before monetizing: avoid CPML (XTTS-v2, commercial license no longer obtainable) and CC-BY-NC (F5-TTS), and avoid unverified "royalty-free" music. Stock APIs (Pexels/Pixabay) give **no copyright indemnification** — you bear the risk.
- **YouTube's automation / "inauthentic content" policies** matter: mass-produced, low-effort AI content risks demonetization under YouTube Partner Program rules, which were tightened through 2025. Quality and genuine value still gate monetization. Verify against current YPP terms, which evolve.
- **Several retention statistics are creator-analytics heuristics, not official YouTube figures** (e.g. "70% at 30s," "3s logo costs 8–15%," "+15–25% from pattern interrupts," "40–60% vs 25–35% retention"). Treat as directional and validate with your own YouTube Studio retention data.
- **pytrends and TikTok Creative Center scraping are unofficial** and can break or rate-limit; the official Google Trends API is alpha with tight quotas, and TikTok scraping should use only public data.
- **Kokoro's "#1 on TTS Arena" is leaderboard-dependent** — it leads among browser-runnable/consumer-hardware models, but on the full Artificial Analysis TTS Arena it ranks ~32nd of 74 (Elo ~1056). Benchmark on your own audio before committing. Other vendor "X% preferred over ElevenLabs" figures come from vendor-run studies and should be discounted accordingly.
- **Claude Code SKILL.md specifics evolve** — verify `.claude/skills/` discovery, `allowed-tools`, plugin/hook behavior, and scheduling against current Anthropic docs for your installed version.