---
name: yt-script
description: Write a genuinely original, high-retention long-form (8-20 min) YouTube script with cited sources, a consistent channel POV, chapters, and flagged mid-roll points. Produces project/<slug>/script.json for the render spine, behind a required human approval gate. Use when a topic has been chosen and a long-form script is needed.
---

# yt-script

Turns a chosen topic into a validated `project/<slug>/script.json` the render
spine (voice -> media -> captions -> stitch) consumes. The creative work
(research, synthesis, writing) is done by **you, Claude, following this file**.
The deterministic parts (assembly, duration math, validation, the review
summary) are tested Python in `scripts/write_script.py`.

This is **not** a black-box auto-generator. A **human approval gate** before any
rendering is what keeps the channel monetizable under YouTube's July-2025
inauthentic-content policy. Never skip it.

## Run
`python .claude/skills/yt-script/scripts/write_script.py <slug>`

- reads `project/<slug>/draft.json` (the content YOU drafted)
- computes `word_count` + `estimated_duration_min`
- validates against the long-form contract (`pipeline/longform.py`) using `channel.json`
- writes `project/<slug>/script.json` only if compliant; else returns the errors
- prints the review summary + the standard `{"success": ...}` envelope

## Read first
`channel.json` — the locked channel identity. Every script must carry this
channel's voice and a clear, original point of view. Read `niche`, `target_audience`,
`channel_pov`, `voice`, `target_length_min`, `pacing_wpm`, `min_sources`, and the
`authenticity_requirements`. They are non-negotiable.

## Script structure (the retention framework)
- **Hook (0-30s):** a concrete promise or outcome, a pattern interrupt, tease the
  payoff. Never "hey guys / welcome back," never just restate the title.
- **Context bridge (~60-90s):** why this matters now, what they walk away with, a
  credibility beat.
- **3-6 core segments:** each is setup -> development -> payoff, with an open loop /
  re-hook at every transition so attention resets.
- **Mid-roll points (`midroll_beats`):** at natural breakpoints, first one ~40-50%
  through, placed AFTER a resolution (never mid-payoff). Tease what's next right
  before each.
- **Re-hook** near the midpoint.
- **Conclusion + CTA.**
- **Pacing** ~130-150 wpm; total 8-20 min (~1,100-2,800 words). Beats ~25-60 words
  each so b-roll switches naturally -> roughly 25-50 beats.
- **Chapters** (>=4) for YouTube navigation, each `{title, start_beat}`.

## Channel POV & authenticity (the monetization moat — non-negotiable)
- Every script carries the channel's consistent voice and an **original take/opinion**:
  synthesis and analysis, not a restatement of one source. This is what makes it
  "transformative."
- **Cite real, verifiable sources. NEVER fabricate a statistic, quote, or citation.**
  If web-research tools are available, use them and cite what you actually found.
  If not, write from knowledge but set `verified: false` on every source and **flag
  fast-changing facts** (tool pricing, feature lists, model versions, free-tier
  limits) for human verification before publish — this niche goes stale fast.
- Be materially specific (real tool behavior, real tradeoffs, real examples), not
  generic filler.
- Need >= `channel.min_sources` (default 5) cited sources, and a per-video
  `channel_pov` (the one-line take THIS video argues — distinct from the channel-level POV).

## draft.json contract (what YOU write)
```json
{
  "title": "...",
  "hook": "...",
  "channel_pov": "one-line take/angle THIS video argues",
  "beats": [
    { "id": 1, "narration": "...", "b_roll_keywords": ["...","..."],
      "on_screen_text": "...", "chapter": "Intro" }
  ],
  "outro": "...",
  "cta": "...",
  "chapters": [ { "title": "...", "start_beat": 1 } ],
  "midroll_beats": [ 14, 24 ],
  "sources": [ { "claim": "...", "source": "...", "url": "...", "verified": false } ],
  "products": [ { "name": "Granola", "beats": [4, 5, 6] } ]
}
```
Beat `id`s must be **unique positive integers**. `word_count` and
`estimated_duration_min` are computed for you — do not set them.
`fixtures/longform_draft.json` is a complete worked example.

### `products[]` — name the tools this video reviews (enables yt-capture)
If the script names specific products (a review/comparison video), emit a
`products` array: one entry per product, with the **body-beat ids that mention
it**. Downstream, `yt-capture` turns each into the real product website on screen
(behind a human URL gate); generic beats keep stock b-roll.
- `name` must be non-empty; every `beats` id must be a real body beat in this
  script (validation rejects a typo or a card id 0/-1).
- `products` is **optional and additive** — omit it for non-product videos. Existing
  scripts without it still validate; `yt-capture --init` falls back to detecting
  proper nouns. Only fields here are `name` + `beats`; URLs are confirmed later at
  GATE 3, not written by you here.

## Process & the human gate
1. **Research** the topic; synthesize an **original POV**. Use web tools if available.
2. **Draft** to the structure above; write it to `project/<slug>/draft.json`.
3. **Run** `write_script.py <slug>`. If it returns validation errors (too short,
   too few sources, missing chapters/midroll/POV, bad beat ids), revise the draft
   and re-run until clean.
4. **HUMAN APPROVAL GATE (REQUIRED):** present the `review_summary` (title, POV,
   chapters, beat count, duration, sources) and **STOP** for explicit approval before
   any rendering. Do not auto-proceed to voice/media/captions/stitch. Call out any
   `verified: false` sources and fast-changing facts that need human checking.

The creative generation is reviewed at the gate, not unit-tested. The Python is
tested in `tests/test_write_script.py`.
