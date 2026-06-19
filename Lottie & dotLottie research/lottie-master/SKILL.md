---
name: lottie-master
description: >-
  Toolkit for everything Lottie and dotLottie — generating animations from
  scratch in Python with no design tools, optimizing and validating them,
  bundling .lottie files, integrating into any web or mobile framework, and
  finding free animations to download. Use this whenever the user mentions
  Lottie, dotLottie, ".lottie", LottieFiles, Bodymovin, or asks to create, add,
  build, or generate an animated loader, spinner, progress bar, animated icon,
  toggle, success/error checkmark, heartbeat, or motion graphic — or asks where
  to get free animations, how to embed one in React, Vue, Svelte, Next.js, plain
  web, React Native, Flutter, iOS, or Android, or how to shrink, optimize, or
  fix an existing animation file. Strongly prefer this skill over hand-writing
  animation JSON or guessing at player APIs from memory.
---

# Lottie master

Everything needed to **research, generate, optimize, bundle, integrate, and
source** Lottie animations — without design software. Four tested scripts, nine
ready templates, and six deep-dive references.

## What Lottie is (10-second version)
A **Lottie** is a small JSON file describing a vector animation (keyframed shapes
— scales to any size, recolors at runtime, far lighter than GIF/video). A
**dotLottie** (`.lottie`) is a zip that bundles one or more animations plus
optional themes, fonts, and interactive state machines. Modern players render
**both** `.json` and `.lottie`. Full background: `references/json-format.md` and
`references/dotlottie-and-bundling.md`.

---

## Decision tree — start here

**The user wants to CREATE an animation**
- A common UI piece (loader, spinner, dots, check, cross, progress, heartbeat,
  bounce, fade-in) → run a **preset**: `python scripts/lottie_gen.py <preset> --color "#hex" -o out.json`. Done in one command.
- Something custom but code-shaped → use the **builder library** inside
  `lottie_gen.py`; see `references/creating-animations.md` (Route A).
- Richer/illustration-grade or needs GIF export → `python-lottie` library, Route B
  in the same reference. Hand-tweaking existing JSON → Route C + `references/json-format.md`.
- They'd rather author visually → point them to no-code editors, Route D.

**The user HAS a file and wants to USE it in a project**
→ `references/integration.md`. Has copy-paste players for web component, vanilla
JS, React, Next.js (SSR-safe), Vue, Svelte, React Native, Flutter, iOS, Android,
plus performance knobs. Pick the player matching their stack.

**The user wants to FIND / download an animation or get inspiration**
→ `references/inspiration-and-sources.md` (free sites + license guidance), then
`python scripts/fetch_lottie.py <url-or-path> --info` to inspect and pull it.

**The user wants a `.lottie` bundle (multiple anims, themes, state machines)**
→ `references/dotlottie-and-bundling.md`; build with
`node scripts/make_dotlottie.mjs --out bundle.lottie a.json b.json`.

**The animation is too big or janky, or you need to validate it**
→ `references/optimization.md`; shrink with
`python scripts/lottie_optimize.py in.json -o out.min.json`.

---

## Quick start — a custom loader in one line
```bash
python scripts/lottie_gen.py spinner --color "#5B8DEF" -o loader.json
```
Then drop it into a page with the web component (no build step):
```html
<script src="https://unpkg.com/@lottiefiles/dotlottie-wc@latest/dist/dotlottie-wc.js" type="module"></script>
<dotlottie-wc src="loader.json" autoplay loop style="width:200px;height:200px"></dotlottie-wc>
```
That's it. For React/Vue/Next/etc., see `references/integration.md`.

---

## The scripts (`scripts/`)
All four are tested and self-contained. Python scripts are **stdlib-only** unless
noted.

| Script | Does | Invoke |
|--------|------|--------|
| **`lottie_gen.py`** | Generate Lottie from scratch — 9 presets **and** a reusable builder API. The centerpiece. | `python scripts/lottie_gen.py <preset> [--color #hex] [--size px] [-o out.json]` · `… list` to see presets |
| **`lottie_optimize.py`** | Shrink + clean `.json`/`.lottie` (round precision, strip metadata, minify). | `python scripts/lottie_optimize.py <in> -o <out> [-p 3] [--keep-names]` |
| **`fetch_lottie.py`** | Download/open a Lottie from URL or path; `--info` report; extract from `.lottie`. | `python scripts/fetch_lottie.py <src> [--info] [--extract first|all] [-o out]` |
| **`make_dotlottie.mjs`** | Bundle one+ `.json` into a `.lottie`. Needs `npm i @dotlottie/dotlottie-js`. | `node scripts/make_dotlottie.mjs --out b.lottie [--loop] [--autoplay] a.json …` |

**Presets** (`lottie_gen.py`): `spinner`, `pulse`, `dots`, `check`, `cross`,
`progress`, `heartbeat`, `bounce`, `fadein`. Every preset takes `--color` and
`--size`.

## The references (`references/`) — read on demand
| File | When to open it |
|------|-----------------|
| `creating-animations.md` | Choosing how to build; using the builder library & `python-lottie`. |
| `json-format.md` | Decoder ring for the JSON — hand-author, recolor, debug, surgically edit. |
| `integration.md` | Embedding in any framework + runtime performance. |
| `dotlottie-and-bundling.md` | `.lottie` internals, bundling, themes, state machines. |
| `optimization.md` | Validate, shrink, and make playback smooth. |
| `inspiration-and-sources.md` | Free download sites + the all-important license caveats. |

## Bundled templates (`assets/templates/`)
Nine production-ready `.json` files, all generated by `lottie_gen.py`, all <3 KB:
`spinner`, `pulse`, `dots-loader`, `success-check`, `error-cross`, `progress-bar`,
`heartbeat`, `bounce`, `fade-in`. Use them as instant drop-ins or as worked
examples to study/modify. Regenerate any of them in a new color with the matching
preset.

---

## Golden rules
- **Generate before you hunt.** For standard UI motion, `lottie_gen.py` is faster
  than searching a library and sidesteps all licensing — code you author is yours.
- **Verify every downloaded file's license individually.** "Free site" ≠ "free
  file"; free often means attribution-required or non-commercial. See the sources
  reference.
- **Modern players load both formats.** Don't convert `.json`→`.lottie` unless you
  need bundling, themes, or state machines.
- **`.json` units that trip people up:** opacity & scale are `0–100` (not 0–1),
  colors are `0–1` RGB floats, origin is top-left with **y down**, time is in
  frames. The generator handles this; remember it when hand-editing.
- **Validate after optimizing**, and pause animations off-screen in production.
- **Next.js / SSR:** the player touches `window`; import it client-side only
  (`dynamic(..., { ssr:false })`). The integration reference shows the pattern.
- When unsure which player or how a prop behaves, **read `integration.md`** rather
  than guessing the API — versions and prop names matter.
