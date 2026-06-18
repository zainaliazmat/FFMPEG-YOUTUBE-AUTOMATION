# Product-Website Capture + Rights Gate — Design

**Date:** 2026-06-19
**Status:** Approved (brainstorm), pending spec review
**Branch:** feat/yt-script-phase2

## Problem

The current pipeline (`discover → script → voice → media → captions → stitch`) produces
videos with a strong script but **generic, unrelated visuals**. The `yt-media` stage
fetches one royalty-free stock clip per beat keyed off generic `b_roll_keywords`
(e.g. `"video call laptop"`). When the narration says "First up, Granola," the viewer
sees a stranger typing on a laptop — not Granola. For a review/comparison channel,
the *actual product* must appear on screen.

## Goal

Automatically capture and display the **real product websites** as B-roll, using a
headless Chromium browser (Playwright), in a way that is **defensible against copyright
claims** for a monetized "honest-verdict" review channel.

Form decision (locked): **high-resolution screenshots + the existing Ken Burns
(zoompan) path** — not screen recordings. Architected so a motion/recording path can be
added later without redesign.

## Research baseline (2026-06-19, adversarially verified)

Full report: deep-research task `wcksm030p`. Key verified findings that this design
encodes:

- **Showing product-site screenshots inside a genuine review is well-supported US fair
  use.** Criticism/comment is a statutorily favored, transformative purpose;
  **monetization does not bar fair use** (*Campbell v. Acuff-Rose*, 510 U.S. 569).
  Post-*Warhol* (2023), the use must serve a **different purpose** than the original —
  a critique vs. the product's own marketing — which this format does.
- **Content ID risk for website stills is LOW.** Content ID is overwhelmingly an audio
  fingerprinting system (~98% of claims automatic; music dominates). Generic
  third-party website UI footage typically is **not eligible** as a Content ID
  reference asset. A Content ID claim is **not** a copyright strike — strikes come only
  from formal DMCA removal requests.
- **The "2–3 seconds is automatically safe" belief is a debunked MYTH** (US Copyright
  Office + YouTube). There is **no** duration/percentage safe-harbor. Duration is a
  pacing choice, **never** a legal shield, and this design does not treat it as one.
- **What actually reduces risk (automatable):** (1) transformative commentary/voiceover
  context — already present; (2) cropped / partial / reduced-size / picture-in-picture
  rather than full-screen 1:1 reproduction (*Bill Graham v. Dorling Kindersley*,
  448 F.3d 605 — reduced size kept the "amount" factor neutral); (3) avoid the site's
  own marketing **video** assets and any embedded music (the real Content ID exposure);
  (4) do not reproduce paywalled/logged-in content; (5) attribution is courtesy, **not**
  a defense.
- **Residual unknowns** (flagged, not resolved; US-only analysis): website
  Terms-of-Service / scraping legality, robots.txt relevance, and trademark/logo
  nominative fair use. Low practical risk for public marketing homepages, but tracked.

## Architecture

Two new stages are inserted:

```
discover → script → capture → voice → media → rights → captions → stitch
```

- **`yt-capture`** (new): after `script.json` exists, resolves the named products to
  official URLs (human-gated), drives Playwright to grab high-res stills into
  `media/`, and logs each into `manifest.json`. Runs *alongside* `yt-media`, not
  instead of it — product-mention beats get the real site; generic beats keep stock
  b-roll.
- **`yt-rights`** (new): a compliance gate that runs after capture + media and before
  stitch. It applies a deterministic rule engine (framing/crop/PiP, reject the site's
  own video/audio, paywall check), refreshes a cached snapshot of canonical
  copyright-policy pages, and writes a per-project `rights_report.json` audit trail. It
  **gates** stitch: an asset that cannot be made defensible is dropped back to stock
  b-roll.

Each stage is independently runnable, idempotent (skips if its manifest stage is
`done` unless `--force`), and emits the standard JSON envelope on stdout + `.result.json`,
matching the existing skills.

### Honest scope of `yt-rights`

`yt-rights` is **compliance automation + an audit trail, not legal advice**, and it
reduces — does not eliminate — claim risk. It encodes the verified doctrine above
(not the duration myth), enforces the framing tactics deterministically, and keeps a
dated record of what policy said at publish time. `rights_report.json` carries this
disclaimer in its header.

## Component 1: `yt-capture`

### Inputs
- `project/<slug>/script.json` (existing)
- `project/<slug>/products.json` (produced by this stage, then human-confirmed)

### Product → URL resolution (3 steps)

1. **Extract candidates.** Going forward, `yt-script` emits a `products` array into
   `script.json`: `[{name, beats:[ids]}]`. Fallback for existing scripts (including
   the current `ai-meeting-tools-worth-paying-2026`): capitalized proper-noun
   detection across each beat's `narration` + `on_screen_text`.
2. **Resolve to URLs — HUMAN GATE.** The stage writes a proposed
   `project/<slug>/products.json` with best-guess URLs and `"confirmed": false`. The
   user reviews/fixes the URLs and sets `"confirmed": true`. Capture **refuses** to run
   on unconfirmed entries, so a wrong/parked/clone domain never gets silently recorded.
   ```json
   [{ "name": "Granola", "url": "https://www.granola.ai/",
      "pages": ["https://www.granola.ai/", "https://www.granola.ai/pricing"],
      "beats": [4,5,6], "confirmed": false }]
   ```
3. **Capture.** Per confirmed product, per page: load, dismiss cookie/consent banner,
   wait for `networkidle` + web fonts, grab a `deviceScaleFactor: 2` **viewport** still
   (hero region — not a giant full-page capture, which doesn't fit a 16:9 Ken Burns
   pan), save PNG to `media/`. A product mentioned in N beats can receive up to N
   different shots (homepage / pricing / feature) so the same logo does not repeat.

### Capture settings (from Playwright official docs + 2026 anti-bot analysis)
- Public **marketing homepages only** — the lowest-risk capture scenario (these pages
  want to be seen and indexed). No aggressive evasion needed.
- Realistic user-agent + viewport (1920×1080), `deviceScaleFactor: 2` for crisp stills.
- Wait for `networkidle` and `document.fonts.ready` before capture; small settle delay
  for above-the-fold animations.
- Cookie/consent dismissal: try a small list of common "Reject all"/"Accept" selectors;
  if none match, proceed (banner may be cropped out by the rights-stage framing anyway).
- Fallback escalation if a site blocks (Cloudflare/Datadome): retry headful, then with
  `playwright-stealth`/`patchright`. If still blocked, record a `capture_failed` note
  and let that beat fall back to stock b-roll. Never hard-fail the pipeline.

### Outputs
- PNG stills in `project/<slug>/media/`.
- `manifest.json` `stages.capture`: per asset → `{ product, source_url, page,
  captured_at, file, beats:[ids], status }`, plus `notes` for failures.
- Standard JSON envelope on stdout + `.result.json`.

### Run
`python .claude/skills/yt-capture/scripts/capture_sites.py <slug> [--force]`

Idempotent: skips if stage `capture` is `done` unless `--force`. Refuses if
`products.json` has unconfirmed entries (prints which).

## Component 2: `yt-rights`

Runs after capture + media, before captions/stitch. For each captured asset it
produces a verdict and a transformed-if-needed file, then writes `rights_report.json`.

### Per-asset rule engine (deterministic)

| Rule | Action | Doctrine basis |
|---|---|---|
| Full-screen 1:1 reproduction | Crop to a region OR composite as picture-in-picture on a branded card — never full-bleed raw | *Bill Graham* — reduced size keeps "amount" neutral |
| Asset is the site's own `<video>`/embedded player | **Reject** → fall back to stock b-roll | Real Content ID exposure is their video/music |
| Embedded audio present | Strip (stills carry none; guards the future motion path) | Audio ≈ 98% of Content ID claims |
| URL paywalled / behind login | **Reject** | Do not reproduce gated content |
| Transformative context present | Pass; flag any beat with no narration | Criticism = favored, transformative purpose |
| Attribution | Logged as courtesy — **never** counted as a defense | "Credit ≠ fair use" |

The crop/PiP transform is the primary, always-applied lever: every product still is
reframed so the final on-screen asset is not a raw full-bleed reproduction of someone
else's page.

### Policy-freshness ("stay current like a lawyer")

On each run, `WebFetch` a fixed canonical set — YouTube "copyright myths" + Content ID
help pages, copyright.gov/fair-use — and diff against a cached snapshot under
`.cache/rights/`. If wording changed since the last publish, flag it in the report as
"policy text changed, re-review." The stage ships with today's verified doctrine baked
in as the baseline; it surfaces change, it does **not** invent legal conclusions. If a
fetch fails (offline), it uses the cached snapshot and notes the staleness.

### Outputs — `rights_report.json`
- Header: disclaimer (compliance automation + audit trail, not legal advice; reduces
  not eliminates risk), policy-snapshot date.
- Per asset: source URL, capture date, treatment applied (crop / PiP / reject), the
  fair-use rationale string, beat ids.
- Top-level: `verdict: "ship" | "review"`, plus residual flags (ToS, robots.txt,
  trademark) surfaced for human awareness.
- Standard JSON envelope on stdout + `.result.json`.

### Gating behavior
- `verdict: ship` → stitch proceeds with the (transformed) product assets.
- Any asset rejected → that beat's `manifest` entry reverts to its stock b-roll asset
  so stitch always has a usable visual; never a blank beat.
- `verdict: review` (e.g. a policy page changed, or a residual flag the engine can't
  clear) → the stage exits non-zero with a clear message; the human resolves and re-runs.

### Run
`python .claude/skills/yt-rights/scripts/apply_rights.py <slug> [--force]`

Idempotent: skips if stage `rights` is `done` unless `--force`.

## Data flow

```
script.json ──► yt-capture ──► products.json (HUMAN GATE: confirm URLs)
                    │
                    ├─► media/*.png (product stills)
                    └─► manifest.json stages.capture
                                        │
stock b-roll ◄── yt-media ──────────────┤
                                        ▼
                                   yt-rights  ──► rights_report.json (audit trail)
                                        │         (crop/PiP transforms applied)
                                        ▼
                                 captions → stitch  ──► out/video_16x9.mp4
```

The existing `yt-stitch` Ken Burns / zoompan path consumes the product stills exactly
like any other still — no stitch redesign required. Per-beat asset selection in stitch
prefers a product still when the beat has one and the rights gate passed; otherwise the
stock b-roll asset.

## Testing

- **`yt-capture`:** unit test product extraction from a fixture `script.json`; unit
  test the `confirmed:false` refusal path; integration test against 1–2 stable public
  homepages (gated/marked slow, network-dependent) asserting a non-empty PNG of the
  expected dimensions and a logged manifest entry. Cookie-banner dismissal tested
  against a recorded fixture page where feasible.
- **`yt-rights`:** unit test each rule (full-screen → crop produces smaller dims;
  `<video>` asset → reject + stock fallback recorded; paywall URL → reject; missing
  narration → flag). Unit test policy-diff using two cached snapshot fixtures (changed
  vs unchanged). Test `verdict` gating: rejected asset reverts manifest to stock;
  changed-policy yields `review` + non-zero exit. Assert `rights_report.json` schema
  and disclaimer header.
- **End-to-end:** re-render the current `ai-meeting-tools-worth-paying-2026` project and
  confirm product beats now show the real sites (gated/slow).

## Out of scope (YAGNI)

- Screen-recording / motion capture path (designed-for, not built now).
- 9:16 specific reframing beyond what stitch already does.
- Trademark/ToS legal *resolution* — surfaced as flags only; not adjudicated.
- Any automated dispute/appeal filing to YouTube.
- Non-US copyright regimes (UK/EU fair dealing).

## Residual risks (documented, accepted)

- Fair use is fact-specific; no tool guarantees zero claims. `yt-rights` reduces, not
  eliminates, exposure.
- ToS/scraping and trademark questions are unverified by the research and surfaced as
  flags, not cleared.
- Anti-bot blocking on some sites may force a stock-b-roll fallback for that product.
