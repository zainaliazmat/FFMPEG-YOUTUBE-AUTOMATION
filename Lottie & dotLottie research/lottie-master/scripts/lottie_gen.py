#!/usr/bin/env python3
"""
lottie_gen.py — a dependency-free Lottie (.json) generator.

Why this exists: Lottie JSON uses cryptic abbreviated keys (ty, ks, ip, op, sh...).
This module hides that behind readable builders so Claude (or you) can assemble
valid, player-ready Lottie animations from primitives + eased keyframes, with NO
pip installs required. It emits Lottie schema v5.x JSON that loads in lottie-web,
@lottiefiles/dotlottie-web, lottie-react, lottie-ios, lottie-android, etc.

Two ways to use it:
  1) As a library:  from lottie_gen import Lottie, ellipse, fill, ...
  2) As a CLI for ready presets:
       python lottie_gen.py spinner   --color "#5B8DEF" --size 200 -o spinner.json
       python lottie_gen.py pulse     --color "#22C55E" -o pulse.json
       python lottie_gen.py dots      --color "#111827" -o dots.json
       python lottie_gen.py check     --color "#22C55E" -o check.json
       python lottie_gen.py cross     --color "#EF4444" -o cross.json
       python lottie_gen.py progress  --color "#5B8DEF" -o progress.json
       python lottie_gen.py heartbeat --color "#EF4444" -o heart.json
       python lottie_gen.py bounce    --color "#F59E0B" -o bounce.json
       python lottie_gen.py fadein    --color "#5B8DEF" -o fade.json
       python lottie_gen.py list      # print all presets

Coordinates: Lottie's origin (0,0) is the TOP-LEFT of the canvas; y grows downward.
Colors: Lottie stores RGB as 0..1 floats. Use hex() to convert "#RRGGBB".
Opacity/scale: 0..100 (NOT 0..1). Rotation: degrees.
"""
from __future__ import annotations
import argparse
import copy
import json
import math
import sys
from typing import Any

# --------------------------------------------------------------------------- #
# Easing presets. Each tuple is a CSS cubic-bezier (p1x, p1y, p2x, p2y).
# In Lottie a keyframe's `o` = out handle of THIS keyframe, `i` = in handle of
# the NEXT keyframe; together they ease the segment between them.
# --------------------------------------------------------------------------- #
EASE = {
    "linear":        (0.0, 0.0, 1.0, 1.0),
    "ease":          (0.25, 0.1, 0.25, 1.0),
    "easeIn":        (0.42, 0.0, 1.0, 1.0),
    "easeOut":       (0.0, 0.0, 0.58, 1.0),
    "easeInOut":     (0.42, 0.0, 0.58, 1.0),
    "easeInOutSine": (0.37, 0.0, 0.63, 1.0),
    "easeOutCubic":  (0.33, 1.0, 0.68, 1.0),
    "easeInCubic":   (0.32, 0.0, 0.67, 0.0),
    "easeOutBack":   (0.34, 1.56, 0.64, 1.0),   # slight overshoot — great for pops
    "easeOutElastic":(0.16, 1.30, 0.30, 1.0),
}


def hex(color: str) -> list[float]:
    """'#5B8DEF' or '5B8DEF' (or with alpha) -> [r,g,b] floats in 0..1."""
    c = color.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    r = int(c[0:2], 16) / 255.0
    g = int(c[2:4], 16) / 255.0
    b = int(c[4:6], 16) / 255.0
    return [round(r, 4), round(g, 4), round(b, 4)]


# --------------------------------------------------------------------------- #
# Property builders (the {a, k} value objects Lottie expects everywhere).
# --------------------------------------------------------------------------- #
def static(value: Any) -> dict:
    """A non-animated property value."""
    return {"a": 0, "k": value}


def animated(keyframes: list[tuple]) -> dict:
    """An animated property.

    keyframes: list of (time, value, easing_name) OR (time, value) for the
    final keyframe / hold. `value` is a number or list. Easing applies to the
    segment LEAVING that keyframe. Use 'hold' as easing for stepped changes.
    """
    out = []
    kfs = [kf if len(kf) == 3 else (kf[0], kf[1], None) for kf in keyframes]
    for idx, (t, val, ease) in enumerate(kfs):
        v = val if isinstance(val, list) else [val]
        kf: dict = {"t": t, "s": v}
        is_last = idx == len(kfs) - 1
        if not is_last:
            if ease == "hold":
                kf["h"] = 1
            else:
                p1x, p1y, p2x, p2y = EASE[ease or "easeInOut"]
                kf["o"] = {"x": [p1x], "y": [p1y]}
                kf["i"] = {"x": [p2x], "y": [p2y]}
        out.append(kf)
    return {"a": 1, "k": out}


# --------------------------------------------------------------------------- #
# Transform block (used by layers and by group `tr`).
# --------------------------------------------------------------------------- #
def transform(anchor=(0, 0), position=(0, 0), scale=(100, 100),
              rotation=0, opacity=100) -> dict:
    def prop(v):
        return v if isinstance(v, dict) else static(list(v) if isinstance(v, tuple) else v)
    return {
        "a": prop(anchor),
        "p": prop(position),
        "s": prop(scale),
        "r": prop(rotation),
        "o": prop(opacity),
        "sk": static(0),
        "sa": static(0),
    }


# --------------------------------------------------------------------------- #
# Shape primitives. Each returns one Lottie shape dict.
# Pass a dict (from animated()) instead of a plain value to animate any field.
# --------------------------------------------------------------------------- #
def ellipse(size=(80, 80), position=(0, 0), name="ellipse") -> dict:
    return {"ty": "el", "nm": name, "d": 1,
            "s": size if isinstance(size, dict) else static(list(size)),
            "p": position if isinstance(position, dict) else static(list(position))}


def rect(size=(80, 80), position=(0, 0), roundness=0, name="rect") -> dict:
    return {"ty": "rc", "nm": name, "d": 1,
            "s": size if isinstance(size, dict) else static(list(size)),
            "p": position if isinstance(position, dict) else static(list(position)),
            "r": roundness if isinstance(roundness, dict) else static(roundness)}


def star(points=5, position=(0, 0), outer=50, inner=25, rotation=0,
         polygon=False, name="star") -> dict:
    s = {"ty": "sr", "nm": name, "d": 1, "sy": 2 if polygon else 1,
         "pt": static(points),
         "p": position if isinstance(position, dict) else static(list(position)),
         "r": rotation if isinstance(rotation, dict) else static(rotation),
         "or": outer if isinstance(outer, dict) else static(outer),
         "os": static(0)}
    if not polygon:
        s["ir"] = inner if isinstance(inner, dict) else static(inner)
        s["is"] = static(0)
    return s


def path(vertices, in_tangents=None, out_tangents=None, closed=True, name="path") -> dict:
    """A free-form bezier path. vertices/tangents are lists of [x,y].
    in/out tangents are RELATIVE to each vertex (default straight lines)."""
    n = len(vertices)
    i = in_tangents or [[0, 0]] * n
    o = out_tangents or [[0, 0]] * n
    return {"ty": "sh", "nm": name, "d": 1,
            "ks": static({"i": i, "o": o, "v": vertices, "c": closed})}


def fill(color="#000000", opacity=100, name="fill") -> dict:
    return {"ty": "fl", "nm": name,
            "c": color if isinstance(color, dict) else static(hex(color) if isinstance(color, str) else color),
            "o": opacity if isinstance(opacity, dict) else static(opacity), "r": 1}


def stroke(color="#000000", width=4, opacity=100, cap="round", join="round", name="stroke") -> dict:
    caps = {"butt": 1, "round": 2, "square": 3}
    joins = {"miter": 1, "round": 2, "bevel": 3}
    return {"ty": "st", "nm": name,
            "c": color if isinstance(color, dict) else static(hex(color) if isinstance(color, str) else color),
            "o": opacity if isinstance(opacity, dict) else static(opacity),
            "w": width if isinstance(width, dict) else static(width),
            "lc": caps.get(cap, 2), "lj": joins.get(join, 2), "ml": 4}


def gradient_fill(stops, start=(0, 0), end=(0, 100), radial=False, name="gradient") -> dict:
    """stops: list of (offset0to1, '#RRGGBB'). Builds a linear/radial gradient fill."""
    flat = []
    for off, col in stops:
        r, g, b = hex(col) if isinstance(col, str) else col
        flat += [off, r, g, b]
    return {"ty": "gf", "nm": name, "t": 2 if radial else 1, "r": 1,
            "o": static(100),
            "s": static(list(start)), "e": static(list(end)),
            "g": {"p": len(stops), "k": static(flat)}}


def trim(start=0, end=100, offset=0, name="trim") -> dict:
    """Trim Path — animate start/end (0..100) to 'draw' strokes. Great for line art."""
    return {"ty": "tm", "nm": name, "m": 1,
            "s": start if isinstance(start, dict) else static(start),
            "e": end if isinstance(end, dict) else static(end),
            "o": offset if isinstance(offset, dict) else static(offset)}


def group(shapes: list[dict], tr: dict | None = None, name="group") -> dict:
    """Bundle shapes; an optional transform `tr` moves/scales the whole group."""
    items = list(shapes)
    items.append({"ty": "tr", **(tr or transform())})
    return {"ty": "gr", "nm": name, "it": items}


def repeater(copies=6, offset=0, anchor=(0, 0), position=(0, 0),
             scale=(100, 100), rotation=0, name="repeater") -> dict:
    """Duplicate the shapes above it `copies` times with an incremental transform.
    Perfect for radial spinners, dot rings, etc."""
    return {"ty": "rp", "nm": name,
            "c": static(copies), "o": static(offset), "m": 1,
            "tr": {"a": static(list(anchor)), "p": static(list(position)),
                   "s": static(list(scale)), "r": static(rotation),
                   "so": static(100), "eo": static(100),
                   "ty": "tr"}}


# --------------------------------------------------------------------------- #
# Layer + Animation builders.
# --------------------------------------------------------------------------- #
class Lottie:
    def __init__(self, width=512, height=512, fps=60, duration_frames=60, name="animation"):
        self.w, self.h, self.fr = width, height, fps
        self.op = duration_frames
        self.name = name
        self.layers: list[dict] = []

    def shape_layer(self, shapes: list[dict], tr: dict | None = None,
                    name="shape", in_frame=0, out_frame=None) -> dict:
        layer = {
            "ddd": 0, "ind": len(self.layers) + 1, "ty": 4, "nm": name, "sr": 1,
            "ks": tr or transform(position=(self.w / 2, self.h / 2)),
            "ao": 0, "shapes": shapes, "ip": in_frame,
            "op": self.op if out_frame is None else out_frame, "st": 0, "bm": 0,
        }
        self.layers.append(layer)
        return layer

    def to_dict(self) -> dict:
        return {
            "v": "5.7.0", "fr": self.fr, "ip": 0, "op": self.op,
            "w": self.w, "h": self.h, "nm": self.name, "ddd": 0,
            "assets": [], "layers": list(reversed(self.layers)),  # last added = on top
        }

    def save(self, out_path: str, minify=True) -> str:
        with open(out_path, "w") as f:
            if minify:
                json.dump(self.to_dict(), f, separators=(",", ":"))
            else:
                json.dump(self.to_dict(), f, indent=2)
        return out_path


# --------------------------------------------------------------------------- #
# Presets — readable recipes that double as worked examples.
# --------------------------------------------------------------------------- #
def preset_spinner(color="#5B8DEF", size=200) -> Lottie:
    """A rotating 3/4 ring (classic loading spinner) via a trimmed circle stroke."""
    a = Lottie(size, size, fps=60, duration_frames=60, name="spinner")
    c = size / 2
    ring = ellipse(size=(size * 0.6, size * 0.6), position=(0, 0))
    s = stroke(color, width=size * 0.08, cap="round")
    t = trim(start=static(0), end=static(75),
             offset=animated([(0, 0, "linear"), (60, 360)]))  # spin the arc
    spin_tr = transform(position=(c, c),
                        rotation=animated([(0, 0, "linear"), (60, 360)]))
    a.shape_layer([ring, s, t], tr=spin_tr, name="ring")
    return a


def preset_pulse(color="#22C55E", size=200) -> Lottie:
    """A dot that scales + fades outward, like a 'live'/ping indicator."""
    a = Lottie(size, size, fps=60, duration_frames=60, name="pulse")
    c = size / 2
    ring = ellipse(size=(size * 0.4, size * 0.4), position=(0, 0))
    f = fill(color)
    tr = transform(
        position=(c, c),
        scale=animated([(0, [40, 40], "easeOut"), (60, [120, 120])]),
        opacity=animated([(0, 80, "easeOut"), (60, 0)]),
    )
    a.shape_layer([ring, f], tr=tr, name="ping")
    # solid center dot on top
    dot = ellipse(size=(size * 0.28, size * 0.28), position=(0, 0))
    a.shape_layer([dot, fill(color)], tr=transform(position=(c, c)), name="dot")
    return a


def preset_dots(color="#111827", size=240) -> Lottie:
    """Three dots bouncing in sequence (typing / loading indicator)."""
    a = Lottie(size, int(size * 0.4), fps=60, duration_frames=60, name="dots")
    cy = size * 0.2
    r = size * 0.06
    gap = size * 0.22
    x0 = size / 2 - gap
    for i in range(3):
        d = ellipse(size=(r * 2, r * 2), position=(0, 0))
        delay = i * 8
        tr = transform(
            position=(x0 + i * gap, cy),
            scale=animated([
                (delay, [100, 100], "easeInOut"),
                (delay + 12, [150, 150], "easeInOut"),
                (delay + 24, [100, 100], "easeInOut"),
                (60, [100, 100]),
            ]),
            opacity=animated([
                (delay, 40, "easeInOut"),
                (delay + 12, 100, "easeInOut"),
                (delay + 24, 40, "easeInOut"),
                (60, 40),
            ]),
        )
        a.shape_layer([d, fill(color)], tr=tr, name=f"dot{i+1}")
    return a


def preset_check(color="#22C55E", size=200) -> Lottie:
    """A success checkmark that draws itself in, inside a circle."""
    a = Lottie(size, size, fps=60, duration_frames=45, name="check")
    c = size / 2
    # circle outline draws in first
    circ = ellipse(size=(size * 0.72, size * 0.72), position=(0, 0))
    circ_stroke = stroke(color, width=size * 0.06)
    circ_trim = trim(start=static(0),
                     end=animated([(0, 0, "easeOut"), (24, 100)]))
    a.shape_layer([circ, circ_stroke, circ_trim],
                  tr=transform(position=(c, c), rotation=-90), name="circle")
    # the tick (3 points), drawn after the circle
    pts = [[-size * 0.16, 0], [-size * 0.04, size * 0.13], [size * 0.20, -size * 0.14]]
    tick = path(pts, closed=False)
    tick_stroke = stroke(color, width=size * 0.07, cap="round", join="round")
    tick_trim = trim(start=static(0),
                     end=animated([(18, 0, "easeOut"), (40, 100)]))
    a.shape_layer([tick, tick_stroke, tick_trim],
                  tr=transform(position=(c, c)), name="tick")
    return a


def preset_cross(color="#EF4444", size=200) -> Lottie:
    """An error cross (X) that draws in, inside a circle."""
    a = Lottie(size, size, fps=60, duration_frames=45, name="cross")
    c = size / 2
    circ = ellipse(size=(size * 0.72, size * 0.72), position=(0, 0))
    a.shape_layer([circ, stroke(color, width=size * 0.06),
                   trim(start=static(0), end=animated([(0, 0, "easeOut"), (24, 100)]))],
                  tr=transform(position=(c, c), rotation=-90), name="circle")
    d = size * 0.16
    for idx, pts in enumerate([[[-d, -d], [d, d]], [[d, -d], [-d, d]]]):
        line = path(pts, closed=False)
        a.shape_layer([line, stroke(color, width=size * 0.07, cap="round"),
                       trim(start=static(0),
                            end=animated([(18 + idx * 6, 0, "easeOut"), (40, 100)]))],
                      tr=transform(position=(c, c)), name=f"line{idx+1}")
    return a


def preset_progress(color="#5B8DEF", size=320) -> Lottie:
    """A rounded progress bar filling 0 -> 100%."""
    h = max(16, int(size * 0.06))
    a = Lottie(size, h * 3, fps=60, duration_frames=72, name="progress")
    cy = h * 1.5
    track = rect(size=(size * 0.9, h), position=(0, 0), roundness=h)
    a.shape_layer([track, fill("#E5E7EB")], tr=transform(position=(size / 2, cy)), name="track")
    barw = size * 0.9
    bar = rect(size=animated([(0, [0, h], "easeInOut"), (72, [barw, h])]),
               position=animated([(0, [-barw / 2, 0], "easeInOut"), (72, [0, 0])]),
               roundness=h)
    a.shape_layer([bar, fill(color)], tr=transform(position=(size / 2, cy)), name="bar")
    return a


def preset_heartbeat(color="#EF4444", size=200) -> Lottie:
    """A heart shape with a double-thump beat."""
    a = Lottie(size, size, fps=60, duration_frames=60, name="heartbeat")
    c = size / 2
    scale = size * 0.018
    # Classic heart curve: x=16sin^3 t, y=13cos t-5cos2t-2cos3t-cos4t.
    # Sample densely into a smooth closed polygon (Lottie smooths short segments).
    verts = []
    for k in range(48):
        t = 2 * math.pi * k / 48
        x = 16 * math.sin(t) ** 3
        y = 13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)
        verts.append([round(x * scale, 2), round(-y * scale, 2)])  # -y: Lottie y is down
    heart = path(verts, closed=True)
    beat = animated([
        (0, [100, 100], "easeOut"), (8, [118, 118], "easeIn"),
        (16, [100, 100], "easeOut"), (24, [112, 112], "easeIn"),
        (32, [100, 100], "linear"), (60, [100, 100]),
    ])
    a.shape_layer([heart, fill(color)],
                  tr=transform(anchor=(0, 0), position=(c, c), scale=beat), name="heart")
    return a


def preset_bounce(color="#F59E0B", size=240) -> Lottie:
    """A ball bouncing with squash & stretch."""
    a = Lottie(size, size, fps=60, duration_frames=60, name="bounce")
    c = size / 2
    r = size * 0.16
    ball = ellipse(size=(r * 2, r * 2), position=(0, 0))
    top, bot = r + 8, size - r - 8
    tr = transform(
        position=animated([
            (0, [c, top], "easeIn"), (24, [c, bot], "easeOut"),
            (48, [c, top], "easeIn"), (60, [c, top]),
        ]),
        scale=animated([
            (0, [100, 100], "easeIn"), (22, [100, 100], "linear"),
            (24, [125, 75], "easeOut"), (26, [100, 100], "linear"),
            (48, [100, 100], "linear"), (60, [100, 100]),
        ]),
    )
    a.shape_layer([ball, fill(color)], tr=tr, name="ball")
    return a


def preset_fadein(color="#5B8DEF", size=200) -> Lottie:
    """A square that fades + scales in with a slight overshoot (UI reveal)."""
    a = Lottie(size, size, fps=60, duration_frames=40, name="fadein")
    c = size / 2
    sq = rect(size=(size * 0.5, size * 0.5), position=(0, 0), roundness=size * 0.08)
    tr = transform(
        position=(c, c),
        scale=animated([(0, [60, 60], "easeOutBack"), (30, [100, 100]), (40, [100, 100])]),
        opacity=animated([(0, 0, "easeOut"), (20, 100), (40, 100)]),
    )
    a.shape_layer([sq, fill(color)], tr=tr, name="square")
    return a


PRESETS = {
    "spinner": preset_spinner, "pulse": preset_pulse, "dots": preset_dots,
    "check": preset_check, "cross": preset_cross, "progress": preset_progress,
    "heartbeat": preset_heartbeat, "bounce": preset_bounce, "fadein": preset_fadein,
}


def main(argv=None):
    p = argparse.ArgumentParser(description="Generate Lottie .json animations.")
    p.add_argument("preset", choices=list(PRESETS) + ["list"])
    p.add_argument("--color", default="#5B8DEF", help="primary color hex")
    p.add_argument("--size", type=int, default=0, help="canvas size px (0 = preset default)")
    p.add_argument("-o", "--out", default=None, help="output .json path")
    p.add_argument("--pretty", action="store_true", help="pretty-print (larger file)")
    args = p.parse_args(argv)

    if args.preset == "list":
        for name, fn in PRESETS.items():
            print(f"  {name:10s} {fn.__doc__.strip().splitlines()[0]}")
        return 0

    fn = PRESETS[args.preset]
    kwargs = {"color": args.color}
    if args.size:
        kwargs["size"] = args.size
    anim = fn(**kwargs)
    out = args.out or f"{args.preset}.json"
    anim.save(out, minify=not args.pretty)
    d = anim.to_dict()
    print(f"Wrote {out}  ({len(json.dumps(d))} bytes, {d['w']}x{d['h']}, "
          f"{d['op']/d['fr']:.1f}s @ {d['fr']}fps, {len(d['layers'])} layers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
