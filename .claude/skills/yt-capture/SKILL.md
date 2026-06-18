---
name: yt-capture
description: Capture the REAL product website as B-roll for product-mention beats — press-kit-first, Playwright screenshot as fallback — behind a human URL-confirmation gate. Runs after script.json and alongside yt-media; product beats get the real site, generic beats keep stock b-roll. Use when a review/comparison script names specific products that should appear on screen.
---

# yt-capture

Turns the products a script names into per-beat product stills. Product-mention
beats then show the real site (rendered as a reduced-size PiP card by yt-stitch);
every other beat keeps its stock b-roll from yt-media. Resolution is
**press-kit-first**: a hand-picked local image or an official press/brand-kit URL
beats a live Playwright screenshot, which is the fallback only.

> ⚠ **Read [RIGHTS.md](../../../RIGHTS.md) once before publishing product visuals.**
> It carries the verified fair-use framing and the YouTube dispute procedure. The
> first successful capture run reminds you in its envelope.

## Two-step run (the confirm gate is a hard safety boundary)

```
# 1. scaffold — extracts products from script.json, writes a proposed products.json
python .claude/skills/yt-capture/scripts/capture_sites.py <slug> --init

# 2. edit products.json (verify URLs / add press-kit or image / set confirmed:true)

# 3. capture the confirmed products
python .claude/skills/yt-capture/scripts/capture_sites.py <slug> [--force]
```

`--init` captures nothing — it only writes the scaffold so a wrong/parked/clone
domain never gets silently recorded. Capture **refuses** if nothing is confirmed
(and leaves the stage `pending`, so re-running after you confirm works).

## products.json schema

```json
[{
  "name": "Granola",
  "url": "https://www.granola.ai/",
  "pages": ["https://www.granola.ai/", "https://www.granola.ai/pricing"],
  "press_kit": null,
  "image": null,
  "beats": [4, 5, 6],
  "confirmed": false
}]
```

| field | meaning |
|-------|---------|
| `name` | product name (required) |
| `url` | official homepage; verify it is the real product, not a parked/clone domain |
| `pages` | optional extra pages to capture (homepage / pricing / feature) so one logo doesn't repeat |
| `press_kit` | optional official brand/press-kit image **URL** (https) — licensed-by-intent, stable |
| `image` | optional **local path** to a hand-picked PNG/JPG you already have |
| `beats` | the body-beat ids that mention this product |
| `confirmed` | set `true` ONLY after you verify the source |

**Resolution precedence:** `image` > `press_kit` > Playwright over `pages`/`url`.
All URLs (press-kit and Playwright) are SSRF-checked (`pipeline.urlsafe`): https
only, no internal/loopback/metadata hosts.

### AI-agent recipe (for auto-populating products.json)
1. Take the `products[]` array from `script.json` (or the `--init` scaffold).
2. For each product, web-search `"<name>" official site` and set `url` to the real
   homepage (reject parked domains, app-store pages, search results).
3. Optionally search `"<name>" press kit OR brand assets` and set `press_kit` to an
   official media/press image URL.
4. Leave `image` null unless a local screenshot exists. Set `confirmed: true` only
   after the human reviews, or surface the proposed file for human confirmation.

## Error codes (envelope + per-asset notes)
Every failure carries a typed `code` and a `next_action` / repair hint:

| code | meaning | fix |
|------|---------|-----|
| `unconfirmed_product` | product not confirmed | verify + set `confirmed:true` in products.json |
| `missing_source` | no image, press_kit, or url | add one of them |
| `unsafe_url` | URL failed the SSRF guard | use a public https URL |
| `playwright_blocked` | anti-bot / not installed / nav failed | add a press_kit url or local image |
| `no_usable_image` | captured file is not a valid PNG | check the source returns an image |
| `download_failed` | press-kit download failed / too large | check the URL |

A failed capture is **non-fatal**: that beat falls back to stock b-roll. The
pipeline never hard-fails on a blocked site.

## Notes
- Idempotent: skips if stage `capture` is `done` unless `--force`. `--force` re-runs
  capture but **never** bypasses the `confirmed:true` gate.
- Partial-confirm: confirmed products are captured; unconfirmed ones are skipped with
  a warning and fall back to stock.
- Output: a single JSON envelope on stdout AND `project/<slug>/.result.json`.
- Captured stills carry `framing:"pip"`; yt-stitch renders them as a reduced-size
  card (never full-bleed) — the *Bill Graham* "amount" lever, applied unconditionally.
- Playwright is an **optional** dependency (`pip install playwright && playwright
  install chromium`). Without it, only the press-kit / local-image paths work.
