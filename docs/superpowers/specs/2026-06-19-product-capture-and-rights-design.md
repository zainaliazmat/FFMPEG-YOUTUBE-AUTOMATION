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

---

## Autoplan Review — Accepted Direction (Option A: trim to high-confidence shape)

Reviewed via `/autoplan` on 2026-06-19 (SELECTIVE EXPANSION). At the premise gate the
user chose **Option A**. Cross-model review (Codex + repo-grounded Claude subagent,
6/6 dimensions) converged on trimming the spec. The design the eng/DX phases review and
that implementation should follow is the **trimmed** shape below, which supersedes the
fuller `yt-rights` description above where they conflict.

**`yt-rights` collapses from a stage into a stitch default + a doc:**
- The only rule doing real work on a still is **crop/PiP framing**. Make it an
  **always-on default in `yt-stitch`**: a product still is never rendered full-bleed
  1:1 — it is cropped to a region or composited as PiP on a branded card. This is the
  *Bill Graham* "reduced size" lever, applied unconditionally, no verdict needed.
- **Drop** the deterministic rule engine, the `WebFetch` policy-diff "freshness" oracle,
  and `rights_report.json`-as-legal-shield. Rationale (from the spec's own research):
  stills carry no audio/video, so "reject the site's `<video>`/embedded audio" is dead
  code; the paywall rule duplicates the human URL-confirmation gate; and a policy-diff
  oracle that flips to `verdict: review` on a Google help-page reword blocks the render
  pipeline for zero risk reduction.
- Replace the audit trail with a static **`RIGHTS.md`** the human reads once: the
  verified fair-use doctrine, the framing rule (crop/PiP, no full-bleed), "no paywalled
  content," "no embedded video/audio," "attribution is courtesy not a defense," and a
  one-paragraph **dispute procedure** for the rare Content ID claim (the reactive lever
  the original spec had left out of scope).

**`yt-capture` becomes press-kit-first, Playwright-fallback:**
- At the human URL-confirmation gate, the human may paste a **press/brand-kit URL or a
  hand-picked image** per product. These are licensed-by-intent, stable across redesigns,
  and higher-res than a homepage hero crop.
- Playwright auto-capture is the **fallback** for products with no press kit. The
  anti-bot escalation ladder (headful → stealth → patchright) moves **off the critical
  path**: if a site blocks, log `capture_failed` and fall back to stock b-roll. Never
  hard-fail, never maintain a scraping arms race as the primary path.

**Unchanged from the original spec:** stills + Ken Burns form (locked); human URL gate;
`products[]` array in `script.json`; per-beat asset selection; idempotent JSON-envelope
stages; the verified fair-use research baseline.

**Deferred (the user can revisit):** the broader Codex/subagent reframe — build a
`yt-upload` + `yt-analytics` publish→measure loop *before* deepening production, since
the channel has shipped zero measured videos. Logged below as a P2 TODO; not adopted
this branch per the user's choice of A over C.

<!-- AUTONOMOUS DECISION LOG -->
## Decision Audit Trail

| # | Phase | Decision | Classification | Principle | Rationale | Rejected |
|---|-------|----------|----------------|-----------|-----------|----------|
| 1 | CEO | Mode = SELECTIVE EXPANSION | Mechanical | autoplan override | Feature enhancement on an existing pipeline | EXPANSION / HOLD / REDUCTION |
| 2 | CEO | Premise gate → Option A (trim) | **User Challenge** | user decides | 6/6 cross-model convergence; user chose A | B (as-written), C (reframe) |
| 3 | CEO | yt-rights → crop/PiP default + RIGHTS.md | resolved by A | P5 explicit, P3 pragmatic | Dead-code rules + pipeline-blocking oracle removed | full rule engine + policy oracle |
| 4 | CEO | yt-capture → press-kit-first | resolved by A | P3 pragmatic, P1 completeness | Avoids anti-bot maintenance race | Playwright-primary |
| 5 | CEO | yt-upload/yt-analytics loop → defer to TODO (P2) | Taste | P6 bias to action | User chose A not C; surfaced for later | build now |
| 6 | Eng | Reconciliation (capture beats:[]→singular beat) must be built; "no stitch redesign" is false | Mechanical | P1 completeness | F1 critical; product never reaches video otherwise | leave as-spec'd |
| 7 | Eng | manifest.init must merge, not wipe, existing stages | Mechanical | P5 explicit | F4 critical; re-run data loss | leave as-spec'd |
| 8 | Eng | crop/PiP needs explicit producer→consumer + product-asset tag | Mechanical | P5 explicit | F2; the one surviving rights lever is unbuilt | implicit policy |
| 9 | Eng | SSRF allow-list on confirmed URLs | Mechanical | security non-optional | F13; confirm gate ≠ security boundary | trust the human |
| 10 | Eng | Per-beat asset floor asserted before stitch | Mechanical | P1 completeness | F6; implicit fallback is fragile | rely on media-exhaustive |
| 11 | Eng | Where reconciliation + crop/PiP live (capture-time vs stitch-time) | **Taste** | close approaches | both viable; surfaced at gate | — |
| 12 | DX | Resolve products.json schema + press-kit precedence + examples + agent recipe | Mechanical | P1 completeness | headline feature unusable from doc | leave vague |
| 13 | DX | Split scaffold (`--init`) from capture; partial-confirm; typed error codes | Mechanical | P5 explicit | two-pass no-op friction; zero error strings | two-pass refuse |
| 14 | DX | RIGHTS.md discoverability (SKILL links + first-run note + Last-reviewed) | Mechanical | P1 completeness | static doc invisible to human+agent | loose file |
| 15 | DX | Update yt-pipeline contract + yt-stitch SKILL | Mechanical | P5 explicit | feature invisible to entry point | undocumented |

---

## Phase 3 — Eng Review (dual voices on the trimmed design)

Both voices grounded the review; **Codex degraded to prompt-only** (its `read-only` sandbox failed with `bwrap: loopback: Failed RTM_NEWADDR` and could not open files) so the repo-grounded findings come from the Claude subagent, with Codex independently confirming the same architecture seam from the prompt. Tag: `[codex-degraded + subagent]`.

```
ENG DUAL VOICES — CONSENSUS TABLE
═══════════════════════════════════════════════════════════════════════
  Dimension                          Claude   Codex   Consensus
  ────────────────────────────────── ──────── ─────── ───────────
  1. Architecture sound?             NO       NO      CONFIRMED — integration seam broken (F1)
  2. Test coverage sufficient?       NO       NO      CONFIRMED — zero capture/products/PiP tests
  3. Performance risks addressed?    partial  —       Claude-only (capture size/count caps, F15)
  4. Security threats covered?       NO       —       Claude-only CRITICAL (SSRF, F13) — flagged regardless
  5. Error paths handled?            NO       NO      CONFIRMED — fallback floor implicit (F6)
  6. Deployment risk manageable?     n/a      n/a     local CLI pipeline; no deploy surface
═══════════════════════════════════════════════════════════════════════
```

### Section 1 — Architecture (ASCII)
```
  CURRENT (stitch sees only media):
    fetch_media ─► stages.media.assets [{beat:n, path}]  ──► stitch by_beat[n]
                                                              └─ raises if beat n absent

  TRIMMED DESIGN — the gap (capture output is invisible to stitch):
    yt-capture ─► stages.capture.assets [{beats:[4,5,6], path}]   ── (no consumer)
                                                                   ✗ stitch never reads this
                                                                   ✗ plural beats[] ≠ singular beat

  REQUIRED (add reconciliation + conditional reframe):
    yt-capture ─► capture assets ─┐
                                  ├─► RECONCILE (fan-out beats[]→beat, capture wins,
    fetch_media ─► media assets ──┘    assert every body beat covered) ─► unified list
                                                                            │
                                                       stitch reframes asset.source=="product"
                                                       (crop/PiP, never full-bleed) ─► Ken Burns
```

**Section 2 — Error & Rescue Registry**
```
  CODEPATH                  | FAILURE MODE              | RESCUED? | TEST? | USER SEES        | LOGGED?
  --------------------------|---------------------------|----------|-------|------------------|--------
  capture: confirm gate     | unconfirmed product       | Y (refuse)| GAP  | refusal + fix    | envelope
  capture: Playwright       | anti-bot block / timeout  | Y (stock) | GAP  | warning+fallback | envelope
  capture: URL load         | SSRF / file:// / internal | N ← GAP   | GAP  | (ships in video!)| no  ← F13
  reconcile: beat coverage  | product-only beat, no stock| N ← GAP  | GAP  | ffmpeg crash     | RuntimeError ← F6
  write_script re-run       | wipes stages.capture      | N ← GAP   | GAP  | silent data loss | no  ← F4
  capture: payload          | non-PNG / oversized       | N ← GAP   | GAP  | garbage to zoompan| no ← F16
```
Four CRITICAL/HIGH gaps (RESCUED=N): F13 (SSRF), F6 (floor), F4 (init wipe), F16 (payload validation).

### Sections 3-10 (condensed; full findings in tasks E1-E10)
- **§3 Security:** F13 SSRF allow-list (HIGH, single-voice → flagged). F14 cookie-selector injection (keep selectors hardcoded). §3 has real findings → all routed to tasks.
- **§4 Data/UX edge cases:** partial-confirm undefined; product-only-beat + capture-failed = no asset. Routed to E5/D4.
- **§5 Code quality:** validators ignore unknown fields → green validation, late runtime crash (F7). DRY: reconciliation should reuse the existing `{beat,path,source,license}` asset shape.
- **§6 Tests:** zero coverage; test plan written to `~/.gstack/projects/FFMPEG-YOUTUBE-AUTOMATION/zainaliazmat1-feat-yt-script-phase2-test-plan-*.md` (E10).
- **§7 Performance:** F15 capture has no byte/count cap (existing media stage caps at MAX_BYTES=200MB — match it). Routed to E9.
- **§8 Observability:** capture should log per-product source/attempted-urls/reason in the envelope (D3 typed codes).
- **§9 Deploy:** n/a — local CLI pipeline, no migration/rollout. Idempotency is the analog: F4/E2 is the deploy-equivalent risk.
- **§10 Trajectory:** reversibility 4/5 (stages are additive). Debt: the press-kit schema and reconciliation owner must be pinned now or they calcify.

## Phase 3.5 — DX Review (dual voices)

Product type: CLI pipeline + AI-agent-driven skills. Initial DX **4/10 → target 8/10** (all gaps closeable by spec edits, no architecture change). Codex again prompt-only; both voices converged on every point.

```
DX DUAL VOICES — CONSENSUS TABLE
═══════════════════════════════════════════════════════════════════════
  Dimension                          Claude   Codex   Consensus
  ────────────────────────────────── ──────── ─────── ───────────
  1. Time-to-first-result low?       NO       NO      CONFIRMED — two-pass write/refuse no-op
  2. Schema/inputs guessable?        NO       NO      CONFIRMED — press-kit schema unspecified
  3. Error messages actionable?      NO       NO      CONFIRMED — zero error strings specified
  4. Envelope/--force consistent?    partial  partial CONFIRMED — --force + done-on-refusal undefined
  5. Docs/contract updated?          NO       —       Claude-only — yt-pipeline/yt-stitch SKILL not touched
  6. RIGHTS.md discoverable?         NO       NO      CONFIRMED — invisible to human + agent
═══════════════════════════════════════════════════════════════════════
```
Developer journey (human): script.json → run capture (writes products.json, refuses) → hand-edit + confirm → re-run capture → voice/media/captions/stitch. The two-pass no-op is the friction; `--init` fixes it (D1). AI-agent journey needs JSON-path-level repair hints (D3) and an explicit press-kit recipe (D2).

## Required Outputs

### NOT in scope (deferred, with rationale)
- yt-upload + yt-analytics publish→measure loop — the bigger strategic reframe (option C); user chose A. → T-CEO1 (P2).
- Screen-recording / motion capture path — designed-for, not built (original spec YAGNI, still holds).
- Trademark/ToS legal resolution — surfaced as flags in RIGHTS.md, not adjudicated.
- 9:16 reframing beyond current stitch behavior.
- Automated YouTube dispute filing — but the manual dispute *procedure* is now in scope (RIGHTS.md, D6).

### What already exists (sub-problem → existing code, reuse)
- Per-beat stock asset + hard floor: `fetch_media.py:159,181` (reuse as fallback floor for E5).
- Ken Burns / zoompan still rendering: `stitch_video.py:83-88` (reuse; extend with conditional crop/PiP for E3).
- Asset record shape `{beat,path,source,license}`: `fetch_media.py:196` (reconciliation should reuse, not invent).
- Idempotent stage skip + JSON envelope + `.result.json`: `manifest.stage_done`, `result.run` (reuse for yt-capture).
- Backward-compatible schema (ignores unknown fields): `longform.py` — lets `products[]` ride along, but means E8 validator is needed.

### Dream-state delta
After Option A: production gains real product visuals with a defensible framing default and a low-maintenance press-kit-first path. The measurement half of the publish→measure→iterate loop still does not exist (deferred T-CEO1) — the plan moves production forward but not yet toward the data-driven ideal.

### Failure Modes Registry
See Section 2 table above. CRITICAL GAPS: F4 (init wipe), F6 (asset floor), F13 (SSRF). HIGH: F1 (seam), F2 (crop/PiP), F16 (payload).

## Implementation Tasks
Synthesized from this review. P1 blocks ship; P2 same branch; P3 follow-up. Effort: human / CC.

- [ ] **E1 (P1, ~3h / ~25min) — yt-stitch** — Reconciliation: fan out capture `beats:[ids]` → singular per-beat records, merge into the list stitch consumes (capture wins).
  - Surfaced by: Eng §1 — F1 CRITICAL, `stitch_video.py:165/205`
- [ ] **E2 (P1, ~1h / ~10min) — manifest** — `manifest.init` must merge (not wipe) existing stages; re-running yt-script must not orphan `stages.capture`.
  - Surfaced by: Eng §3 — F4 CRITICAL, `write_script.py:68`
- [ ] **E3 (P1, ~3h / ~25min) — yt-stitch** — Specify+implement crop/PiP transform; tag product assets so reframe is conditional (stock untouched).
  - Surfaced by: Eng §1 — F2 HIGH, `stitch_video.py:83-88`
- [ ] **E4 (P1, ~2h / ~20min) — yt-capture** — SSRF allow-list: https-only, block RFC1918/link-local/loopback, re-check after redirects.
  - Surfaced by: Eng §3 — F13 HIGH
- [ ] **E5 (P1, ~1h / ~10min) — yt-stitch** — Assert per-beat asset floor before stitch so `capture_failed` never reaches `stitch_video.py:182`.
  - Surfaced by: Eng §2 — F6 HIGH
- [ ] **E6 (P2, ~15min / ~5min) — manifest** — Add `capture` to STAGES tuple.
  - Surfaced by: Eng §1 — F3
- [ ] **E7 (P2, ~1h / ~10min) — yt-media** — Define product/stock precedence (media skips confirmed-capture beats or reconciliation owns it).
  - Surfaced by: Eng §4 — F5
- [ ] **E8 (P2, ~1h / ~10min) — schema** — `products[]` validator (name non-empty; beats positive ints existing in script).
  - Surfaced by: Eng §5 — F7
- [ ] **E9 (P2, ~1h / ~10min) — yt-capture** — Capture hardening: byte/dim/count caps, temp-then-validate, PNG magic-byte check.
  - Surfaced by: Eng §7 — F15/F16
- [ ] **E10 (P1, ~3h / ~25min) — tests** — Reconciliation, capture_failed→stock→stitch, products validation, crop/PiP dims, manifest wiring, refusal path.
  - Surfaced by: Eng §6 — F8-F12
- [ ] **D1 (P2, ~1h / ~10min) — yt-capture** — Split `--init` scaffold from capture run.
- [ ] **D2 (P1, ~1h / ~10min) — yt-capture** — Resolve products.json schema + press-kit precedence (image>press_kit>Playwright) + good/bad examples + agent recipe.
- [ ] **D3 (P2, ~1h / ~10min) — yt-capture** — Typed error codes + verbatim messages with `next_action` in the envelope.
- [ ] **D4 (P2, ~30min / ~5min) — yt-capture** — Partial-confirm (capture confirmed, warn+stock the rest); refusal leaves stage `pending`.
- [ ] **D5 (P2, ~20min / ~5min) — yt-capture** — `--force` overwrites derived assets, never bypasses confirmation.
- [ ] **D6 (P2, ~45min / ~10min) — docs** — RIGHTS.md discoverability + concrete dispute procedure + `Last reviewed` header.
- [ ] **D7 (P2, ~30min / ~10min) — yt-pipeline** — Update pipeline contract + yt-stitch SKILL (document always-on reframe).
- [ ] **T-CEO1 (P2, ~3d / ~2h) — pipeline** — Build yt-upload + yt-analytics publish→measure loop (deferred reframe).

### Completion Summary (CEO / Eng / DX)
```
  +====================================================================+
  | /autoplan — COMPLETION SUMMARY (trimmed design, Option A)          |
  +====================================================================+
  | Mode               | SELECTIVE EXPANSION                            |
  | Premise gate       | User Challenge → Option A (trim) chosen        |
  | CEO dual voices    | 6/6 confirmed challenge (codex-degraded+sub)   |
  | Eng dual voices    | 16 findings; 3 CRITICAL gaps (F4,F6,F13)       |
  | Eng consensus      | 4/6 confirmed NO; arch seam F1 cross-confirmed |
  | DX dual voices     | DX 4/10 → 8/10; 6/6 confirmed                  |
  | Design (Sec 11)    | SKIPPED — no UI scope                          |
  | NOT in scope       | written (5 items)                              |
  | What exists        | written (5 reuse points)                       |
  | Failure modes      | 6 mapped, 3 CRITICAL GAPS                      |
  | Test plan          | written to ~/.gstack/.../test-plan-*.md        |
  | Tasks              | 18 (10 eng, 7 dx, 1 ceo-deferred)             |
  | Unresolved         | 1 taste (decision #11: reconcile location)    |
  +====================================================================+
```

### Unresolved decisions
- **#11 (taste):** does the reconciliation + crop/PiP live in yt-capture (produce final per-beat singular records + transformed PNG at capture time) or in yt-stitch (`_render` merges + reframes at render time)? Both viable. Surfaced at the final gate.
