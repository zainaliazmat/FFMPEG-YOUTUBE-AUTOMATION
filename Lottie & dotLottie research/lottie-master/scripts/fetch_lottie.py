#!/usr/bin/env python3
"""
fetch_lottie.py — download (or open) a Lottie and inspect it.

Use it to pull a reference animation from a CDN/share URL so you can study its
structure, recolor it, optimize it, or drop it straight into a project. Works
with both raw .json and .lottie (zip) sources, and with local paths.

Usage:
  python fetch_lottie.py https://lottie.host/<id>/<file>.lottie -o anim.json
  python fetch_lottie.py https://example.com/loader.json -o loader.json
  python fetch_lottie.py ./bundle.lottie --info          # just print a report
  python fetch_lottie.py ./bundle.lottie --extract all -o ./out_dir/

Notes:
  - .lottie archives can hold several animations; --extract all writes each to
    the output directory; default writes the first animation.
  - ALWAYS check the source's license before shipping someone else's animation.
    See references/inspiration-and-sources.md for per-site licensing.
"""
from __future__ import annotations
import argparse
import io
import json
import os
import sys
import urllib.request
import zipfile


def load_bytes(src: str) -> bytes:
    if src.startswith(("http://", "https://")):
        req = urllib.request.Request(src, headers={"User-Agent": "lottie-master/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.read()
    with open(src, "rb") as f:
        return f.read()


def animations_from_lottie(raw: bytes) -> dict[str, dict]:
    """Return {name: animation_dict} from a .lottie zip."""
    out = {}
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = [n for n in z.namelist() if n.endswith(".json") and n != "manifest.json"]
        for n in names:
            key = os.path.splitext(os.path.basename(n))[0]
            out[key] = json.loads(z.read(n))
    return out


def report(anim: dict, label: str = ""):
    fr = anim.get("fr", 0) or 1
    op, ip = anim.get("op", 0), anim.get("ip", 0)
    dur = (op - ip) / fr
    n_layers = len(anim.get("layers", []))
    n_assets = len(anim.get("assets", []))
    size = len(json.dumps(anim))
    has_imgs = any("p" in a and a.get("e", 0) == 0 for a in anim.get("assets", []))
    print(f"  {label}v{anim.get('v','?')}  {anim.get('w')}x{anim.get('h')}  "
          f"{dur:.2f}s @ {fr}fps  layers={n_layers}  assets={n_assets}"
          f"{'  (has raster images!)' if has_imgs else ''}  {size:,} B")


def main(argv=None):
    p = argparse.ArgumentParser(description="Fetch/inspect a Lottie (.json or .lottie).")
    p.add_argument("src", help="URL or local path")
    p.add_argument("-o", "--out", default=None, help="output .json file or directory")
    p.add_argument("--info", action="store_true", help="print a report, don't write files")
    p.add_argument("--extract", choices=["first", "all"], default="first")
    args = p.parse_args(argv)

    raw = load_bytes(args.src)
    is_zip = args.src.endswith(".lottie") or (len(raw) > 4 and raw[:2] == b"PK")

    if is_zip:
        anims = animations_from_lottie(raw)
        if not anims:
            sys.exit("No animations found in .lottie")
        print(f"{args.src}  ({len(raw):,} B, dotLottie archive, {len(anims)} animation(s))")
        for name, a in anims.items():
            report(a, label=f"[{name}] ")
        if args.info:
            return 0
        if args.extract == "all":
            out_dir = args.out or "."
            os.makedirs(out_dir, exist_ok=True)
            for name, a in anims.items():
                fp = os.path.join(out_dir, f"{name}.json")
                json.dump(a, open(fp, "w"), separators=(",", ":"))
                print(f"  wrote {fp}")
        else:
            name, a = next(iter(anims.items()))
            fp = args.out or f"{name}.json"
            json.dump(a, open(fp, "w"), separators=(",", ":"))
            print(f"  wrote {fp}")
    else:
        a = json.loads(raw)
        print(f"{args.src}  (raw Lottie JSON)")
        report(a)
        if args.info:
            return 0
        fp = args.out or "animation.json"
        json.dump(a, open(fp, "w"), separators=(",", ":"))
        print(f"  wrote {fp}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
