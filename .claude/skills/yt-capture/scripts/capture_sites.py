"""yt-capture — put the REAL product on screen as B-roll.

Trimmed design (autoplan Option A): press-kit-first, Playwright-fallback. The
copyright posture is NOT a rule engine — it is (a) an always-on crop/PiP framing
default that lives in yt-stitch, and (b) a static RIGHTS.md the human reads once.
This stage's only job is to produce per-beat product stills and log them.

Two-step contract (the confirm gate is a hard safety boundary):

  1.  python capture_sites.py <slug> --init
      Extracts the products this script mentions (from script.json's `products`
      array, or a proper-noun fallback) and writes a PROPOSED
      project/<slug>/products.json with `confirmed: false`. Captures nothing.

  2.  python capture_sites.py <slug>
      For every CONFIRMED product, resolves an asset by precedence
      image > press_kit > Playwright(pages/url), validates each URL against SSRF
      (pipeline.urlsafe), saves a PNG into media/, and writes
      manifest stages.capture.assets with framing:"pip" so stitch renders it as a
      reduced-size PiP card. Unconfirmed products are SKIPPED with a warning and
      fall back to stock b-roll (partial-confirm); the stage is only marked `done`
      when at least the confirmed set was processed. A failed/blocked capture is
      logged as capture_failed and also falls back to stock — it NEVER hard-fails
      the pipeline.

Idempotent: skips if stage `capture` is `done` unless --force. A refusal/dry
--init never marks the stage done. Emits the standard JSON envelope + .result.json.

⚠ Read RIGHTS.md once before publishing product visuals (fair-use framing +
the YouTube dispute procedure).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pipeline import result, manifest, schema, urlsafe  # noqa: E402

# Error codes carried in the envelope + per-asset notes so the human AND the AI
# agent get a typed, actionable reason (autoplan DX D3).
ERR_UNCONFIRMED = "unconfirmed_product"
ERR_MISSING_SOURCE = "missing_source"
ERR_UNSAFE_URL = "unsafe_url"
ERR_PLAYWRIGHT_BLOCKED = "playwright_blocked"
ERR_DOWNLOAD_FAILED = "download_failed"
ERR_BAD_IMAGE = "no_usable_image"

VIEWPORT = {"width": 1920, "height": 1080}
DEVICE_SCALE = 2
# Find the official logo IN the page (authoritative + crisp — far better
# provenance/quality than scraping a random copy off image search). Constrained
# to the top header strip (top < 220px) and a denylist that rejects the common
# false positives a naive selector grabs: G2/Capterra review badges, award
# ribbons, and hero illustrations. Returns the source asset to re-render.
_FIND_LOGO_JS = r"""() => {
  const deny = /badge|g2crowd|\bg2\b|capterra|trustpilot|award|review|rating|stars?|press|partner|client|testimonial|hero|illustration|screenshot|avatar/i;
  const sels = ["header a[href] img","header a[href] svg","nav a[href] img",
    "nav a[href] svg","[class*=logo i] img","[class*=logo i] svg",
    "header img","header svg"];
  for (const s of sels) {
    for (const el of document.querySelectorAll(s)) {
      const r = el.getBoundingClientRect();
      if (r.width < 40 || r.height < 12 || r.top > 220 || r.left > 600) continue;
      const meta = [el.getAttribute('alt'), el.getAttribute('src'),
        el.className && el.className.baseVal !== undefined ? el.className.baseVal : el.className,
        el.getAttribute('aria-label')].join(' ');
      if (deny.test(meta)) continue;
      if (el.tagName.toLowerCase() === 'img') {
        const src = el.currentSrc || el.src || el.getAttribute('data-src') || '';
        if (src) return {type:'img', src};
      } else {
        return {type:'svg', html: el.outerHTML};
      }
    }
  }
  return null;
}"""
MAX_PNG_BYTES = 25_000_000          # a 1920x1080@2x PNG is well under this
CONSENT_SELECTORS = (               # hardcoded constants only — never from products.json
    "button#onetrust-accept-btn-handler",
    "button[aria-label='Accept all']",
    "button[aria-label='Reject all']",
    "text=Accept all", "text=Reject all", "text=Accept",
)
# Fallback consent killer: remove known CMP containers, then any fixed/sticky
# overlay whose text mentions cookies/consent. Scoped to fixed/sticky so real
# page content is left alone. Hardcoded — never sourced from products.json.
_HIDE_CONSENT_JS = """() => {
  ['#onetrust-consent-sdk','#onetrust-banner-sdk','#CybotCookiebotDialog',
   '.cky-consent-container','.cky-overlay','#usercentrics-root',
   '#cookiescript_injected','#cookie-banner','#cookie-consent'
  ].forEach(s => document.querySelectorAll(s).forEach(e => e.remove()));
  const cookieish = s => /cookie|consent|gdpr/i.test(s || '');
  // role=dialog / aria-modal cookie modals (covers custom non-CMP modals).
  document.querySelectorAll('[role=dialog],[aria-modal=true]').forEach(el => {
    if (cookieish(el.textContent)) el.remove();
  });
  // Any positioned (non-static) overlay whose OWN text is short and cookie-ish:
  // find the smallest such element and remove its positioned ancestor.
  document.querySelectorAll('div,section,aside').forEach(el => {
    const cs = getComputedStyle(el);
    const t = (el.textContent || '');
    if (cs.position !== 'static' && t.length < 1200 && cookieish(t)
        && /accept|reject|agree|allow|preferences/i.test(t)) {
      el.remove();
    }
  });
}"""
_STOPWORDS = {
    "The", "This", "That", "These", "Those", "And", "But", "For", "First",
    "Next", "Then", "Now", "Today", "Here", "There", "When", "What", "Why",
    "How", "Our", "Your", "My", "We", "You", "It", "If", "So", "Up", "First",
    "Let", "I", "A", "An", "In", "On", "At", "To", "Of",
}


# ----------------------------------------------------------- pure / testable

def _body_beat_ids(script):
    return [b["id"] for b in script.get("beats", []) if isinstance(b.get("id"), int)]


def proper_noun_products(script):
    """Fallback extraction: capitalized proper nouns across each beat's narration
    + on_screen_text, mapped to the beats that mention them. Heuristic, not
    perfect — the human fixes it at the confirm gate."""
    hits = {}
    for b in script.get("beats", []):
        bid = b.get("id")
        text = f"{b.get('narration', '')} {b.get('on_screen_text', '')}"
        # Capitalized runs WITHOUT spanning sentence punctuation (no '.' in the
        # token class), then trim leading/trailing stopwords so "Granola. The"
        # collapses to "Granola" and a bare "The"/"Then" drops out entirely.
        for m in re.finditer(r"[A-Z][A-Za-z0-9&+-]*(?:\s+[A-Z][A-Za-z0-9&+-]*)*", text):
            words = m.group(0).split()
            while words and words[0] in _STOPWORDS:
                words.pop(0)
            while words and words[-1] in _STOPWORDS:
                words.pop()
            name = " ".join(words)
            if len(name) < 3:
                continue
            hits.setdefault(name, set()).add(bid)
    return [{"name": n, "beats": sorted(bs)} for n, bs in sorted(hits.items())]


def extract_products(script):
    """Prefer the script's explicit `products` array; else proper-noun fallback."""
    declared = script.get("products")
    if isinstance(declared, list) and declared:
        return [{"name": p.get("name"), "beats": p.get("beats", [])} for p in declared]
    return proper_noun_products(script)


def proposed_products_json(products):
    """The scaffold written by --init: best-guess URL, all fields, confirmed:false."""
    out = []
    for p in products:
        slug = re.sub(r"[^a-z0-9]+", "", (p["name"] or "").lower())
        out.append({
            "name": p["name"],
            "url": f"https://www.{slug}.com/" if slug else "",
            "pages": [],
            "press_kit": None,   # optional: official brand/press-kit URL (https)
            "image": None,       # optional: local PNG/JPG path you hand-picked
            "beats": p.get("beats", []),
            "confirmed": False,  # set true ONLY after you verify url/press_kit/image
        })
    return out


def partition_confirmed(products):
    confirmed = [p for p in products if p.get("confirmed") is True]
    unconfirmed = [p for p in products if p.get("confirmed") is not True]
    return confirmed, unconfirmed


def resolve_source(product):
    """Precedence: a hand-picked local image, else a press-kit URL, else the
    pages/url for Playwright. Returns (mode, value) or ('none', None)."""
    if product.get("image"):
        return "image", product["image"]
    if product.get("press_kit"):
        return "press_kit", product["press_kit"]
    pages = product.get("pages") or ([product["url"]] if product.get("url") else [])
    if pages:
        return "playwright", pages
    return "none", None


# ------------------------------------------------------------ capture (IO)

def _validate_png(path):
    data = Path(path).read_bytes()[:8]
    return data.startswith(b"\x89PNG\r\n\x1a\n")


def _download_image(url, dest):
    import requests
    ok, reason = urlsafe.is_safe_capture_url(url)
    if not ok:
        raise CaptureError(ERR_UNSAFE_URL, f"{url}: {reason}")
    with requests.get(url, timeout=60, stream=True) as r:
        r.raise_for_status()
        total = 0
        with open(dest, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                total += len(chunk)
                if total > MAX_PNG_BYTES:
                    Path(dest).unlink(missing_ok=True)
                    raise CaptureError(ERR_DOWNLOAD_FAILED,
                                       f"{url}: exceeds {MAX_PNG_BYTES} bytes")
                f.write(chunk)


def _render_logo(context, inner_html, logo_dest):
    """Render logo markup on a TRANSPARENT page and screenshot it big + crisp.
    Re-rendering (vs screenshotting the live element) drops the opaque white
    header behind real-site logos and upscales the asset cleanly. Returns True
    on a non-trivial result."""
    p = None
    try:
        p = context.new_page()
        p.set_content(
            '<body style="margin:0;padding:0;background:transparent">'
            f'<div style="display:inline-block">{inner_html}</div></body>',
            wait_until="load")
        el = p.locator("img, svg").first
        el.wait_for(state="visible", timeout=4000)
        # force a big render so the reveal is sharp
        el.evaluate("e => { e.style.width='1200px'; e.style.height='auto'; }")
        p.wait_for_timeout(250)
        box = el.bounding_box()
        if not box or box["width"] < 40 or box["height"] < 12:
            return False
        el.screenshot(path=str(logo_dest), omit_background=True)
        return True
    except Exception:  # noqa: BLE001 - asset didn't load; caller falls back
        return False
    finally:
        if p:
            try:
                p.close()
            except Exception:  # noqa: BLE001
                pass


def _extract_logo(page, logo_dest):
    """Best-effort official-logo grab. Finds the header logo (excluding badges /
    awards / hero art), then re-renders its SOURCE asset transparent so the
    opaque header background is dropped. Returns True on success. Never raises."""
    try:
        found = page.evaluate(_FIND_LOGO_JS)
    except Exception:  # noqa: BLE001
        return False
    if not found:
        return False
    ctx = page.context
    try:
        if found["type"] == "img":
            src = found["src"]
            if src.startswith("data:"):
                return _render_logo(ctx, f'<img src="{src}">', logo_dest)
            if src.startswith("https://"):
                ok, _ = urlsafe.is_safe_capture_url(src)
                return bool(ok) and _render_logo(ctx, f'<img src="{src}">', logo_dest)
            return False
        return _render_logo(ctx, found["html"], logo_dest)
    except Exception:  # noqa: BLE001
        return False


def _screenshot(url, dest, logo_dest=None):
    """Headless Playwright viewport still (+ optional logo). SSRF-checked.
    Returns True if a logo was also captured into ``logo_dest``."""
    ok, reason = urlsafe.is_safe_capture_url(url)
    if not ok:
        raise CaptureError(ERR_UNSAFE_URL, f"{url}: {reason}")
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise CaptureError(ERR_PLAYWRIGHT_BLOCKED,
                           "playwright not installed; add a press_kit url or local "
                           "image to products.json, or `pip install playwright`")
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_context(
                viewport=VIEWPORT, device_scale_factor=DEVICE_SCALE).new_page()
            # `load` is reliable; `networkidle` hangs on sites with persistent
            # connections (analytics/websockets) — Playwright discourages it. We
            # wait for `load`, then best-effort networkidle with a SHORT cap so a
            # chatty site never burns the full timeout (real-test fix: otter.ai).
            page.goto(url, wait_until="load", timeout=45000)
            try:
                page.wait_for_load_state("networkidle", timeout=6000)
            except Exception:  # noqa: BLE001 - chatty site; proceed anyway
                pass
            # Settle FIRST so the consent banner has actually rendered, THEN try to
            # dismiss it (running the loop immediately after goto missed late
            # banners — real-test fix: the granola.ai cookie modal got captured).
            page.wait_for_timeout(1200)
            for sel in CONSENT_SELECTORS:
                try:
                    page.locator(sel).first.click(timeout=1500)
                    page.wait_for_timeout(400)
                    break
                except Exception:  # noqa: BLE001 - banner may be absent
                    continue
            # ALWAYS run the consent killer, even if a click "succeeded": per-site
            # consent UIs vary too much for a click list alone, and a click can
            # match the wrong element (real test: a click succeeded but granola.ai's
            # custom modal + otter.ai's bottom bar survived). Hide known CMP
            # containers + cookie dialogs + positioned cookie overlays. Hardcoded
            # JS only — never sourced from products.json.
            page.evaluate(_HIDE_CONSENT_JS)
            page.wait_for_timeout(200)
            got_logo = _extract_logo(page, logo_dest) if logo_dest else False
            page.screenshot(path=str(dest))
            browser.close()
            return got_logo
    except CaptureError:
        raise
    except Exception as exc:  # noqa: BLE001 - any nav/anti-bot failure -> fallback
        raise CaptureError(ERR_PLAYWRIGHT_BLOCKED, f"{url}: {exc}")


class CaptureError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code
        self.message = message


def capture_one(product, media_dir, project_dir):
    """Resolve + materialize one product's still. Returns an asset dict
    (framing:'pip') or raises CaptureError with a typed code."""
    mode, value = resolve_source(product)
    name = product["name"]
    fname = re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_") or "product"
    dest = Path(media_dir) / f"product_{fname}.png"
    logo_dest = Path(media_dir) / f"logo_{fname}.png"
    if mode == "none":
        raise CaptureError(ERR_MISSING_SOURCE,
                           f"{name}: no image, press_kit, or url to capture")
    logo_ok = False
    if mode == "image":
        src = Path(value)
        if not src.is_file():
            raise CaptureError(ERR_BAD_IMAGE, f"{name}: image not found: {value}")
        dest.write_bytes(src.read_bytes())
        source_url = f"file://{src.resolve()}"
    elif mode == "press_kit":
        _download_image(value, dest)
        source_url = value
    else:  # playwright over pages -> first that succeeds (also grabs the logo)
        last = None
        for url in value:
            try:
                logo_ok = _screenshot(url, dest, logo_dest)
                source_url = url
                break
            except CaptureError as e:
                last = e
        else:
            raise last
    if not _validate_png(dest):
        Path(dest).unlink(missing_ok=True)
        raise CaptureError(ERR_BAD_IMAGE, f"{name}: captured file is not a PNG")

    # Logo: prefer an auto-extracted one; else a human-provided products.json
    # `logo` (local path). None -> the beat just shows the website PiP (no reveal).
    logo_rel = None
    if logo_ok and _validate_png(logo_dest):
        logo_rel = str(logo_dest.relative_to(project_dir))
    elif product.get("logo"):
        lp = Path(product["logo"])
        if lp.is_file():
            logo_dest.write_bytes(lp.read_bytes())
            if _validate_png(logo_dest):
                logo_rel = str(logo_dest.relative_to(project_dir))

    return {
        "beats": product.get("beats", []),
        "path": str(dest.relative_to(project_dir)),
        "logo": logo_rel,          # transparent logo PNG, or None
        "product": name,
        "source_url": source_url,
        "source": mode,
        "framing": "pip",          # stitch renders this as a reduced-size PiP card
    }


# ------------------------------------------------------------ orchestration

def _init(slug):
    d = manifest.project_dir(slug)
    script_path = d / "script.json"
    if not script_path.is_file():
        return result.err(f"no script at {script_path}")
    script = json.loads(script_path.read_text())
    errs = schema.validate_products(script.get("products"), _body_beat_ids(script))
    if errs:
        return result.err("script products[] invalid: " + "; ".join(errs), errors=errs)
    products = extract_products(script)
    pj = proposed_products_json(products)
    (d / "products.json").write_text(json.dumps(pj, indent=2))
    return result.ok(
        artifact="products.json",
        products=len(pj),
        next_action=(f"Edit project/{slug}/products.json: verify each url (or add a "
                     f"press_kit url / local image), then set \"confirmed\": true and "
                     f"re-run `capture_sites.py {slug}`. Read RIGHTS.md first."))


def _capture(slug, force=False):
    d = manifest.project_dir(slug)
    if manifest.stage_done(slug, "capture") and not force:
        return result.ok(skipped=True, stage="capture")
    pj_path = d / "products.json"
    if not pj_path.is_file():
        return result.err(
            f"no products.json — run `capture_sites.py {slug} --init` first",
            error_code=ERR_UNCONFIRMED)
    products = json.loads(pj_path.read_text())
    confirmed, unconfirmed = partition_confirmed(products)

    warnings = []
    for p in unconfirmed:
        warnings.append({"product": p.get("name"), "code": ERR_UNCONFIRMED,
                         "next_action": f"verify + set confirmed:true in {pj_path.name}"})

    assets, notes = [], []
    for p in confirmed:
        try:
            assets.append(capture_one(p, d / "media", d))
        except CaptureError as e:
            notes.append({"product": p.get("name"), "code": e.code,
                          "message": e.message,
                          "effect": "beats fall back to stock b-roll"})

    # Refusal: nothing confirmed at all -> do NOT mark done; the operator must act.
    if not confirmed:
        return result.err(
            f"refused: 0 of {len(products)} products in {pj_path.name} are confirmed",
            error_code=ERR_UNCONFIRMED, warnings=warnings,
            next_action=(f"open project/{slug}/products.json, verify each url (or add "
                         f"press_kit/image), set \"confirmed\": true, then re-run."))

    manifest.set_stage(slug, "capture", status="done", assets=assets,
                       warnings=warnings, notes=notes)
    return result.ok(captured=len(assets), confirmed=len(confirmed),
                     skipped_unconfirmed=len(unconfirmed),
                     failed=len(notes), warnings=warnings, notes=notes,
                     reminder="product visuals captured — review RIGHTS.md "
                              "(fair-use framing + dispute procedure) before publishing")


def main():
    ap = argparse.ArgumentParser(description="Capture real product visuals for a slug")
    ap.add_argument("slug")
    ap.add_argument("--init", action="store_true",
                    help="write a proposed products.json from script.json and exit")
    ap.add_argument("--force", action="store_true",
                    help="re-run capture even if the stage is done (never bypasses "
                         "the confirmed:true gate)")
    args = ap.parse_args()
    if args.init:
        result.run(lambda: _init(args.slug), slug=args.slug)
    else:
        result.run(lambda: _capture(args.slug, args.force), slug=args.slug)


if __name__ == "__main__":
    main()
