# RIGHTS.md — using product visuals defensibly

**Last reviewed: 2026-06-19** (US copyright law only; re-check before a major
publish push or if you receive a claim — there is no automated freshness watcher.)

This is **compliance guidance + a habit, not legal advice**, and it reduces — does
not eliminate — claim risk. It replaces the deterministic "rights engine" that the
design review cut, because on still screenshots that engine was mostly dead code.
Read this once; the framing rule below is enforced automatically by yt-stitch.

## Why product screenshots in a genuine review are defensible
- Criticism/comment is a statutorily favored, **transformative** purpose. A review's
  use serves a *different* purpose than the product's own marketing (*Campbell v.
  Acuff-Rose*, 510 U.S. 569; post-*Warhol* 2023 transformative-purpose test).
- **Monetization does not bar fair use** (*Campbell*).
- **Reduced size keeps the "amount" factor neutral** (*Bill Graham v. Dorling
  Kindersley*, 448 F.3d 605) — which is why we never show a full-bleed 1:1 page.

## What actually reduces risk (and what this repo does about it)
1. **Transformative voiceover/commentary context** — your script provides it. Flag
   any product beat with no narration.
2. **Reduced-size / PiP framing, never full-bleed** — **automatic**: yt-stitch
   renders every `framing:"pip"` product still at ~72% on a branded card. Do not
   disable this for product stills.
3. **Avoid the site's own marketing VIDEO and any embedded music** — this is the real
   Content ID exposure (audio is ~98% of claims). We capture **still screenshots
   only**, so there is no audio/video track to claim.
4. **Don't reproduce paywalled / logged-in content** — capture public marketing pages
   only. The human confirms each URL at the products.json gate.
5. **Attribution is courtesy, not a defense.** Crediting a source does not make a use
   fair.

## The myth we do NOT rely on
"2–3 seconds is automatically safe" is **debunked** (US Copyright Office + YouTube).
There is no duration/percentage safe-harbor. Clip length is a pacing choice, never a
legal shield.

## If you get a Content ID claim (the reactive lever)
A Content ID claim is **not** a copyright strike — it just flags/holds revenue.
Strikes come only from formal DMCA removal requests.
1. In YouTube Studio → Content → the affected video → **Copyright claims**.
2. If the use is your transformative review commentary, **dispute** it: select
   "fair use," and assert it is *transformative criticism/commentary serving a
   different purpose than the original's marketing*, with reduced-size framing.
3. Successful disputes release the held revenue. Keep your source list (the
   products.json `source_url`s) as your record of what was shown and from where.

## Residual risks (documented, accepted — not cleared)
- Fair use is fact-specific; no tool guarantees zero claims.
- Website Terms-of-Service / scraping legality, robots.txt relevance, and
  trademark/logo nominative fair use are **unverified** here. Low practical risk for
  public marketing homepages, but tracked, not resolved. Prefer official press kits,
  which are licensed-by-intent, when available.
- Non-US copyright regimes (UK/EU fair dealing) are out of scope.
