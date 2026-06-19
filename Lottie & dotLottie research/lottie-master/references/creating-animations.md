# Creating Lottie animations

Four routes, fastest-to-richest. Pick by how custom the motion needs to be.

| Route | Best for | Needs |
|-------|----------|-------|
| A. `lottie_gen.py` builder + presets | loaders, icons, UI feedback, anything code-shaped | nothing (stdlib only) |
| B. `python-lottie` library | richer programmatic art, precomps, raster import, GIF export | `pip install lottie` |
| C. Hand-author / edit JSON | tiny tweaks, recolors, surgical fixes | `references/json-format.md` |
| D. No-code editors (Lottie Creator / After Effects) | hand-crafted, illustration-grade motion | a browser or AE |

---

## A. The bundled generator — `scripts/lottie_gen.py` (START HERE)
Dependency-free. Emits valid Lottie v5 `.json` that every player loads. It hides
the cryptic keys behind readable builders and ships ready presets.

**Presets via CLI:**
```bash
python scripts/lottie_gen.py list                       # show all presets
python scripts/lottie_gen.py spinner  --color "#5B8DEF" --size 200 -o spinner.json
python scripts/lottie_gen.py check    --color "#22C55E" -o success.json
python scripts/lottie_gen.py dots     --color "#6B7280" -o typing.json
```
Presets: `spinner, pulse, dots, check, cross, progress, heartbeat, bounce, fadein`.
Each preset's docstring is a worked example — read them to learn the patterns.

**Custom animation via the library API:**
```python
import sys; sys.path.insert(0, "scripts")
from lottie_gen import Lottie, ellipse, rect, fill, stroke, trim, transform, animated, static, hex

a = Lottie(width=200, height=200, fps=60, duration_frames=60, name="ping")
c = 100
# a dot that scales up and fades out
ring = ellipse(size=(60, 60), position=(0, 0))
tr = transform(
    position=(c, c),
    scale=animated([(0, [60, 60], "easeOut"), (60, [160, 160])]),
    opacity=animated([(0, 90, "easeOut"), (60, 0)]),
)
a.shape_layer([ring, fill("#22C55E")], tr=tr, name="ring")
a.save("ping.json")            # minified by default; .save(path, minify=False) to read
```

**The building blocks** (all in `lottie_gen.py`):
- Shapes: `ellipse`, `rect`, `star`, `path` (free bezier), plus paint `fill`,
  `stroke`, `gradient_fill`.
- Modifiers: `trim` (draw-on strokes), `repeater` (radial/grid copies),
  `group` (bundle + move together).
- Motion: `transform(anchor, position, scale, rotation, opacity)` where any arg
  can be a number/tuple (static) OR an `animated([...])` value.
- `animated([(frame, value, easing), ..., (frame, value)])` — easing names:
  `linear, ease, easeIn, easeOut, easeInOut, easeInOutSine, easeOutCubic,`
  `easeInCubic, easeOutBack, easeOutElastic`, or `"hold"` for a stepped change.
- `hex("#RRGGBB")` → `[r,g,b]` 0..1.

**Golden rules the builder already follows (mirror them when hand-coding):**
- Put `fill`/`stroke` AFTER the geometry in the shape list (painter's order).
- Set the layer **anchor** to the shape's pivot so scale/rotate look centered.
- Keep canvas square and the motion centered unless you need otherwise.
- Loop cleanly: make frame 0 and frame `op` identical for seamless `loop`.

## B. `python-lottie` — the power library
Install: `pip install lottie` (optionally `pip install lottie[images]` for PNG/GIF
export via cairo). Use it when you need precomps, masks, raster/SVG import, text,
or to **export previews to GIF/PNG/APNG** for review.

```python
from lottie import objects, Point, Color
from lottie.exporters.core import export_lottie

an = objects.Animation(60)            # 60 frames
an.frame_rate = 60; an.width = an.height = 200
layer = objects.ShapeLayer(); an.add_layer(layer)
circle = objects.Ellipse(); circle.size.value = Point(80, 80)
circle.position.value = Point(100, 100); layer.add_shape(circle)
layer.add_shape(objects.Fill(Color(0.13, 0.77, 0.37)))
layer.transform.scale.add_keyframe(0,  Point(100, 100))
layer.transform.scale.add_keyframe(30, Point(140, 140))
layer.transform.scale.add_keyframe(60, Point(100, 100))
export_lottie(an, "pulse.json")
```
Render a **GIF preview** for a human to eyeball (needs cairo):
```python
from lottie.exporters.gif import export_gif
export_gif(an, "preview.gif", skip_frames=2)   # lower fps = smaller gif
```
Docs decode every JSON key too: <https://lottiefiles.github.io/lottie-docs/>.

## C. Hand-authoring / editing JSON
For one-off tweaks (recolor, retime, swap a value), edit the JSON directly using
`references/json-format.md` as the key reference, then **validate** before shipping
(see `references/optimization.md` for the validation snippet). Don't hand-write a
whole animation from scratch — use route A or B and edit the result.

## D. No-code editors (for illustration-grade, human-crafted motion)
Claude can't drive a GUI, but should recommend these when the user wants
hand-tuned, designerly motion rather than programmatic shapes:

- **Lottie Creator** (free, web) — <https://lottiefiles.com/lottie-creator>.
  Purpose-built for Lottie. Import an SVG, keyframe it on a timeline, add
  **State Machines** (hover/click interactivity, no code) and **Motion Tokens**
  (data-bound properties), then export `.lottie`/`.json`. Best starting point for
  non-developers.
- **Adobe After Effects + Bodymovin / LottieFiles plugin** — the classic pro
  pipeline. Animate in AE, then the plugin renders to Lottie JSON. Caveats:
  convert all Illustrator/SVG/PDF art to **shape layers** (raster/effects that
  Lottie can't represent are dropped), avoid expression-heavy or per-frame
  keyframes (they bloat the file), use parenting to avoid duplicate keyframes.
- **Lottielab**, **SVGator**, **Jitter** — browser-based timeline tools, "Figma
  for motion." Good for quick SVG→Lottie without AE.

When you produce raw `.json` programmatically and the user then wants
interactivity/themes, hand the `.json` to Lottie Creator to add a State Machine,
or bundle to `.lottie` (see `references/dotlottie-and-bundling.md`).
