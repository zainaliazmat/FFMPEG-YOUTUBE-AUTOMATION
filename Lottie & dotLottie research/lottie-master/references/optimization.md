# Optimizing & validating Lottie files

Read this when an animation is **too big**, **janky on device**, or you need to
**confirm it's structurally valid** before shipping. Tool: `scripts/lottie_optimize.py`.

## Validate first (catch broken JSON before it reaches a player)
A player will often fail silently on a malformed file. `python-lottie` parses
into typed objects, so loading is a cheap structural check:

```bash
pip install lottie   # once
python -c "import json; from lottie.objects import Animation; \
Animation.load(json.load(open('anim.json'))); print('valid Lottie ✓')"
```

If that raises, the file is malformed (bad keyframe shape, wrong types, missing
required keys) — fix the structure before debugging the *visuals*. For a
`.lottie`, extract first with `fetch_lottie.py --extract all`, then validate each
`.json`.

## Shrink it: `scripts/lottie_optimize.py`
Works on `.json` and `.lottie`. Rounds float precision, strips editor metadata
(`nm`/`mn`/`cl`/`ln`, `meta`, `props`, …), and minifies whitespace.

```bash
python scripts/lottie_optimize.py anim.json -o anim.min.json
python scripts/lottie_optimize.py anim.json -o anim.min.json -p 2   # harsher rounding
python scripts/lottie_optimize.py bundle.lottie -o bundle.min.lottie
```

- `-p / --precision N` — decimal places to keep (default **3**). `2` is smaller
  but can visibly quantize smooth motion; eyeball the result.
- `--keep-names` — preserve `nm` layer names (useful if your runtime code looks
  layers up by name; otherwise drop them).
- Re-validate the output (snippet above) and re-render a frame to confirm it
  still looks right. Optimization is lossy in precision, never in structure.

## What actually drives Lottie file size
Biggest to smallest lever:

1. **Path keyframe data.** Animated bezier shapes (`sh` with keyframed vertices)
   store every control point on every keyframe. This is almost always the
   dominant cost. Fewer vertices, fewer keyframes, lower precision → big wins.
2. **Embedded raster images.** A PNG baked into the JSON (base64 in `assets`)
   dwarfs everything and **can't be recolored or cleanly scaled**. Replace with
   vector shapes, or accept it isn't a "true" vector Lottie. `fetch_lottie.py
   --info` flags these.
3. **Per-frame keyframes** (a keyframe on every single frame) instead of letting
   easing interpolate between sparse keys. Author with a few keys + easing.
4. **Redundant precision** — coordinates like `123.456789213`. Rounding to 2–3
   decimals is invisible and compounds across thousands of values.
5. **Editor metadata** — names, match-names, comments, `meta`. Pure overhead at
   runtime; strip for production.

## Runtime performance (smooth playback, low CPU)
File size ≠ render cost. Separately:

- **Pick the right renderer.** The modern dotLottie/ThorVG canvas core is fast
  and consistent. With legacy `lottie-web`, the **canvas** renderer generally
  beats **SVG** for complex/animated-path scenes; SVG is fine for simple ones.
- **Pause when off-screen.** Use an `IntersectionObserver` to play only visible
  animations (see `references/integration.md`). Idle loopers are silent CPU drains.
- **Size the canvas to display size** × devicePixelRatio — don't render a 1200px
  canvas into a 48px icon slot.
- **Reduce overdraw.** Many stacked semi-transparent layers and large blurs are
  expensive every frame. Simplify the source art.
- **Offload where supported** — workers / `OffscreenCanvas` keep the main thread
  responsive for heavy scenes.
- **Respect `prefers-reduced-motion`.** Gate autoplay for users who opt out;
  it's an accessibility expectation, not a nicety.

## A sane production pass
1. Validate (parse with `python-lottie`).
2. Inspect (`fetch_lottie.py --info`) — note layer count, duration, raster flags.
3. Optimize (`lottie_optimize.py`, precision 2–3).
4. Re-validate + re-render one frame to confirm fidelity.
5. Bundle to `.lottie` if shipping several or using themes/state machines
   (`references/dotlottie-and-bundling.md`).
6. In-app: pause off-screen, size correctly, honor reduced-motion.
