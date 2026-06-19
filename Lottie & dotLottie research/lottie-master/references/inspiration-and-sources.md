# Where to find Lottie animations (free sources & inspiration)

Read this when the user wants a ready-made animation, asks "where do I get
Lotties," or needs design inspiration rather than something generated from
scratch. Pair it with `scripts/fetch_lottie.py` to pull a file down once you
have a URL.

> **License rule, read first.** "Free site" never means "every file is free."
> Most of these platforms mix free and premium assets *on the same page*, and a
> free download may still require attribution or forbid commercial use. **Always
> open the individual asset's license** before shipping it. When in doubt,
> generate one with `lottie_gen.py` instead — code you author is unambiguously
> yours.

## The sources

| Site | Cost model | Good for | License notes |
|------|-----------|----------|---------------|
| **LottieFiles** (lottiefiles.com) | Huge free tier + premium | The default. Biggest library, in-browser preview, "Free" filter, direct `.json`/`.lottie`/CDN links | Per-file. Free items are often Lottie Simple License; many need attribution. Check each. |
| **IconScout** (iconscout.com) | Free + paid, subscription | Polished animated icons & illustrations; has an explicit **"Free Commercial License"** filter | Use the free-commercial filter to skip the ambiguity. Still verify. |
| **LottieFlow** (lottieflow.io / Webflow community) | **Fully free** | Web UI motion — loaders, toggles, hovers. Customize color/stroke/speed before export | Free for commercial use; among the least encumbered. Still glance at terms. |
| **Icons8 / Ouch!** (icons8.com, ouch.com) | Free w/ attribution, or paid | Cohesive illustration *styles* (whole matching sets) | Free tier requires a backlink/attribution; paid removes it. |
| **Storyset by Freepik** (storyset.com) | Free w/ attribution | Editable illustration scenes, recolorable, exportable to Lottie | Attribution required on free tier. |
| **ShapeFest** (shapefest.com) | Free | Clean, modern, abstract 3D-ish shapes | Generous free terms; confirm current license. |
| **Creattie** (creattie.com) | Subscription, some free | Designer-grade icon/illustration sets with consistent style | Mostly paid; sample the free ones. |
| **Lordicon** (lordicon.com) | Mostly premium, some free | Interactive animated icons with built-in hover/click states | Largely paid; small free set with attribution. |

## Not Lottie, but worth knowing (alternative formats/tools)
- **Rive** (rive.app) — interactive state-machine animations. *Different runtime/format* (`.riv`), not a Lottie. Reach for it when interactivity is the whole point and you're willing to add its player.
- **SVGator**, **Lottielab**, **Jitter** — browser animation editors that **export Lottie**. Good when the user wants to *author visually* and hand you a `.json`.

## Picking by intent
- **UI feedback (spinner, success, error, progress, toggle)** → just generate it (`lottie_gen.py`); faster than searching and licensing.
- **Branded illustration / mascot / hero scene** → Storyset, Icons8, IconScout (editable, stylistically coherent).
- **Web micro-interactions** → LottieFlow (purpose-built, free, customizable inline).
- **Cohesive icon set across a product** → IconScout, Creattie, Lordicon (matched families).

## Downloading once you have a link
`scripts/fetch_lottie.py` takes a URL **or** a local path, handles both `.json`
and `.lottie`, and needs no dependencies.

```bash
# Inspect before committing to it (dimensions, duration, layers, raster warnings)
python scripts/fetch_lottie.py https://lottie.host/<id>/<file>.lottie --info

# Download and normalize to .json
python scripts/fetch_lottie.py https://lottie.host/<id>/<file>.json -o anim.json

# Pull animations out of a .lottie bundle
python scripts/fetch_lottie.py bundle.lottie --extract all -o ./out/
```

### CDN URL patterns
LottieFiles serves public files from **`lottie.host`**. The in-app "share/embed"
panel gives you the canonical URL — copy that. Both `.json` and `.lottie`
endpoints exist for a given asset; modern players load either, so prefer
`.lottie` when offered (smaller, can carry themes/state machines).

> Network note: a sandboxed environment may not be able to reach `lottie.host`
> or other CDNs. If `fetch_lottie.py` can't connect, download in a normal
> browser/network and pass the **local path** to the same script instead.

## Search strategy on LottieFiles
1. Search the concept, then apply the **Free** filter immediately.
2. Preview playback in-page — check it loops cleanly and isn't secretly a raster
   GIF-in-Lottie (use `--info`; raster assets bloat size and block recoloring).
3. Note whether it's tagged for attribution before downloading.
4. Prefer low layer-count, vector-only files — they recolor and optimize well
   (see `references/optimization.md`).
