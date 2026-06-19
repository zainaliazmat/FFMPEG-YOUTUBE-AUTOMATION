# Lottie JSON format, decoded

Lottie stores everything under terse abbreviated keys to save bytes. This is the
decoder ring. Read it when you need to **hand-author, recolor, debug, or surgically
edit** a `.json` animation. For *generating* animations, prefer the builder in
`scripts/lottie_gen.py` (it writes all of this correctly for you).

## Table of contents
1. Coordinate system & value conventions
2. Top-level Animation object
3. Layers (the `layers` array)
4. The transform block (`ks`)
5. Properties: static vs animated, and keyframe easing
6. Shapes (the `shapes` array on a shape layer)
7. Colors
8. Quick recipes (recolor, retime, find a layer)

---

## 1. Coordinate system & value conventions
- Origin `(0,0)` is the **top-left**; **y increases downward**.
- **Opacity** and **scale** are `0..100` (percent), NOT `0..1`.
- **Rotation** is in **degrees**, clockwise.
- **Colors** are `[r, g, b]` floats in `0..1` (see §7).
- **Time** is measured in **frames**, not seconds. Seconds = frames ÷ `fr`.

## 2. Top-level Animation object
```jsonc
{
  "v": "5.7.0",   // schema version (string)
  "fr": 60,        // frame rate (frames per second)
  "ip": 0,         // in point: first frame
  "op": 60,        // out point: last frame (duration = (op-ip)/fr seconds)
  "w": 200,        // width  (px)
  "h": 200,        // height (px)
  "nm": "name",   // name (optional, droppable)
  "ddd": 0,        // 3D flag: 0 = 2D (almost always)
  "assets": [],    // reusable assets: images, precomps (see below)
  "layers": []     // the visual content, drawn TOP-of-array = BOTTOM of z-order
}
```
> ⚠️ Layer order is painter's order: the **first** layer in the array renders
> first (furthest back). The builder reverses insertion order so "last added =
> on top," matching intuition.

`assets` entries are either:
- **Image**: `{ "id": "image_0", "w":.., "h":.., "u":"images/", "p":"img.png", "e":0 }`
  (`e:1` + `p:"data:image/png;base64,..."` means embedded). Raster images bloat
  files and break crisp scaling — prefer pure vector.
- **Precomp**: `{ "id": "comp_0", "layers": [ ... ] }` — a nested layer stack
  referenced by a precomp layer (`ty:0`, `refId:"comp_0"`).

## 3. Layers (the `layers` array)
Every layer shares these keys:
```jsonc
{
  "ty": 4,          // layer TYPE (see table)
  "nm": "Shape 1",  // name (optional)
  "ind": 1,          // unique index, referenced by "parent"
  "parent": 2,       // (optional) inherit transform from layer with this ind
  "sr": 1,           // time stretch (1 = none)
  "ip": 0, "op": 60, // this layer's own in/out frames (can differ from comp)
  "st": 0,           // start time offset (frames)
  "bm": 0,           // blend mode (0 = normal)
  "ao": 0,           // auto-orient along motion path (0/1)
  "ks": { ... },     // TRANSFORM block (§4)
  "shapes": [ ... ]  // ONLY for shape layers (ty:4)
}
```

**Layer types (`ty`):**
| ty | meaning      | key extra field        |
|----|--------------|------------------------|
| 0  | precomp      | `refId`, `w`, `h`      |
| 1  | solid color  | `sc` (hex), `sw`, `sh` |
| 2  | image        | `refId` → asset        |
| 3  | null         | (invisible; for parenting groups of layers) |
| 4  | shape        | `shapes` array (§6)    |
| 5  | text         | `t` (text data)        |

Most vector UI animation uses **shape layers (`ty:4`)** and occasionally **null
layers (`ty:3`)** as parents to move groups together.

## 4. The transform block (`ks`)
Present on every layer (and inside shape groups as `ty:"tr"`).
```jsonc
"ks": {
  "a": {"a":0,"k":[100,100]},  // anchor point (the pivot for rotate/scale)
  "p": {"a":0,"k":[100,100]},  // position
  "s": {"a":0,"k":[100,100]},  // scale % (x,y)
  "r": {"a":0,"k":0},          // rotation degrees
  "o": {"a":0,"k":100},        // opacity 0..100
  "sk": {"a":0,"k":0},         // skew
  "sa": {"a":0,"k":0}          // skew axis
}
```
> Anchor matters: to scale/rotate a shape **about its own center**, the anchor
> must sit at the shape's center, and position places that anchor on the canvas.

## 5. Properties: static vs animated, and keyframe easing
Any property value is an object `{"a": <0|1>, "k": <value-or-keyframes>}`.

**Static** (`a:0`): `k` is the literal value.
```json
{"a":0,"k":[100,100]}
```

**Animated** (`a:1`): `k` is an array of keyframes.
```jsonc
{"a":1,"k":[
  {"t":0,  "s":[100,100], "o":{"x":[0.42],"y":[0]}, "i":{"x":[0.58],"y":[1]}},
  {"t":30, "s":[140,140]}   // final keyframe: just t + s
]}
```
- `t` = frame, `s` = value AT this keyframe (an array, even for scalars: `[0]`).
- `o` = **out** tangent of THIS keyframe; `i` = **in** tangent of the NEXT keyframe.
  Together they define the easing **curve of the segment between** the two
  keyframes. They are CSS cubic-bezier control points: `o={x:[p1x],y:[p1y]}`,
  `i={x:[p2x],y:[p2y]}` for `cubic-bezier(p1x,p1y,p2x,p2y)`.
- `"h":1` on a keyframe = **hold** (step/instant change, no interpolation).
- The **last** keyframe needs only `t` and `s` (no `i`/`o`).

Common easings as `(p1x,p1y,p2x,p2y)`:
`linear (0,0,1,1)` · `easeInOut (.42,0,.58,1)` · `easeOut (0,0,.58,1)` ·
`easeIn (.42,0,1,1)` · `easeOutBack (.34,1.56,.64,1)` (overshoot/pop).

## 6. Shapes (the `shapes` array on a shape layer)
Each shape is `{"ty":"<code>", ...}`. **Order matters**: painters draw top→down,
so place geometry first and `fl`/`st` (paint) BELOW the geometry they color.

| ty   | shape          | key fields |
|------|----------------|-----------|
| `gr` | group          | `it`: array of child shapes + a trailing `{"ty":"tr",...}` group transform |
| `rc` | rectangle      | `s` size, `p` position, `r` corner roundness |
| `el` | ellipse        | `s` size, `p` position |
| `sr` | star/polygon   | `sy` (1=star,2=polygon), `pt` points, `or`/`ir` outer/inner radius, `r` rotation |
| `sh` | bezier path    | `ks` = `{a, k:{i:[],o:[],v:[],c:bool}}` (`v` vertices, `i`/`o` tangents relative to each vertex, `c` closed) |
| `fl` | fill           | `c` color, `o` opacity, `r` fill rule |
| `st` | stroke         | `c` color, `o` opacity, `w` width, `lc`/`lj` cap/join, `ml` miter |
| `gf` | gradient fill  | `t` (1=linear,2=radial), `s`/`e` start/end pts, `g:{p:n,k:{a,k:[off,r,g,b,...]}}` |
| `gs` | gradient stroke| like `gf` + stroke `w` |
| `tm` | trim path      | `s`/`e` start/end 0..100, `o` offset — animate to "draw" strokes |
| `rp` | repeater       | `c` copies, `o` offset, `tr` per-copy transform — radial/grid duplication |
| `tr` | transform      | the group transform (always last in a `gr`'s `it`) |

**Trim path** (`tm`) is the single most useful trick for line-art reveals
(signatures, checkmarks, progress rings): animate `e` from 0→100 to draw a stroke
on, or animate `o` (offset) to spin a dashed arc.

**Repeater** (`rp`) turns one dot into a ring of dots, or one bar into a grid —
animate the parent rotation for radial spinners with almost no data.

## 7. Colors
RGB floats `0..1`. To convert `#RRGGBB`: divide each channel by 255.
`#5B8DEF → [0.357, 0.553, 0.937]`. Add a 4th element for alpha (`[r,g,b,a]`).
`scripts/lottie_gen.py` exposes `hex("#5B8DEF")` to do this.

## 8. Quick recipes
**Recolor every fill to brand blue** (Python):
```python
import json
d = json.load(open("in.json"))
BLUE = [0.357, 0.553, 0.937]
def walk(o):
    if isinstance(o, dict):
        if o.get("ty") == "fl":            # a fill shape
            o["c"]["k"] = BLUE
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
walk(d); json.dump(d, open("out.json","w"), separators=(",",":"))
```
**Slow an animation to half speed**: multiply the top-level `op` by 2 and every
keyframe `t` by 2 (or just set the player's `speed` to 0.5 at runtime — far easier).

**Find which layer is which**: read `layers[].nm`. If names were stripped, render
frames with `scripts/` rasterization or load it in the LottieFiles web editor.
