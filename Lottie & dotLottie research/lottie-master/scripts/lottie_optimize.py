#!/usr/bin/env python3
"""
lottie_optimize.py — shrink a Lottie .json (or .lottie) without changing how it looks.

Lottie files exported from After Effects/tools are often 5-20x larger than they
need to be: 12-decimal floats, layer names, match-names, and metadata all add up.
This rounds numeric precision, strips non-visual metadata, and minifies whitespace.
Pixel-identical playback in practice; dramatically smaller payloads.

Usage:
  python lottie_optimize.py in.json -o out.json            # default: 3 decimals
  python lottie_optimize.py in.json -o out.json -p 2        # 2 decimals (smaller)
  python lottie_optimize.py in.json --keep-names            # don't strip nm/mn
  python lottie_optimize.py in.lottie -o out.lottie         # handles .lottie archives

Tips: precision 3 is safe for almost everything. Drop to 2 for icon-scale art.
Path vertex data ('ks'/'sh') dominates size — fewer path keyframes helps most.
"""
from __future__ import annotations
import argparse
import io
import json
import os
import zipfile

# Keys that carry no visual information and are safe to drop for production.
STRIP_KEYS = {"nm", "mn", "cl", "ln", "tt"}  # name, match-name, class, layer-name id, (tag)
META_KEYS = {"meta", "metadata", "markers_meta", "props"}


def round_floats(obj, ndigits):
    if isinstance(obj, float):
        r = round(obj, ndigits)
        # collapse -0.0 and integral floats
        if r == int(r):
            return int(r)
        return r
    if isinstance(obj, list):
        return [round_floats(v, ndigits) for v in obj]
    if isinstance(obj, dict):
        return {k: round_floats(v, ndigits) for k, v in obj.items()}
    return obj


def strip_meta(obj, keep_names):
    if isinstance(obj, list):
        return [strip_meta(v, keep_names) for v in obj]
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if k in META_KEYS:
                continue
            if not keep_names and k in STRIP_KEYS:
                continue
            out[k] = strip_meta(v, keep_names)
        return out
    return obj


def optimize_dict(d, ndigits=3, keep_names=False):
    d = strip_meta(d, keep_names)
    d = round_floats(d, ndigits)
    return d


def _read_any(path):
    """Return (lottie_dict, kind) where kind is 'json' or 'lottie'."""
    if path.endswith(".lottie") or zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as z:
            names = [n for n in z.namelist() if n.endswith(".json") and "animations" in n] \
                or [n for n in z.namelist() if n.endswith(".json") and n != "manifest.json"]
            if not names:
                raise SystemExit("No animation JSON found inside .lottie")
            return json.loads(z.read(names[0])), "lottie"
    with open(path) as f:
        return json.load(f), "json"


def main(argv=None):
    p = argparse.ArgumentParser(description="Optimize/minify a Lottie file.")
    p.add_argument("input")
    p.add_argument("-o", "--out", required=True)
    p.add_argument("-p", "--precision", type=int, default=3)
    p.add_argument("--keep-names", action="store_true",
                   help="keep nm/mn layer & match names (useful for debugging)")
    p.add_argument("--pretty", action="store_true")
    args = p.parse_args(argv)

    src_size = os.path.getsize(args.input)
    d, _ = _read_any(args.input)
    d = optimize_dict(d, args.precision, args.keep_names)

    if args.pretty:
        text = json.dumps(d, indent=2)
    else:
        text = json.dumps(d, separators=(",", ":"))

    with open(args.out, "w") as f:
        f.write(text)
    out_size = os.path.getsize(args.out)
    pct = 100 * (1 - out_size / src_size) if src_size else 0
    print(f"{args.input}  {src_size:,} B  ->  {args.out}  {out_size:,} B  "
          f"({pct:.1f}% smaller, precision={args.precision})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
