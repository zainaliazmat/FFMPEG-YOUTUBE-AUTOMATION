"""yt-stitch — assemble the final video with pure FFmpeg.

Corrected build (overrides the plan's buggy Task-5 code):

C1  The timeline covers the FULL voiceover (hook + every beat + outro), not just
    body beats. Hook (id 0) / outro (id -1) have no b-roll, so they get a
    generated title card sized to their narration duration. The hook/outro TEXT
    is passed in via per-segment card text files.
C2  zoompan renders at the TARGET dimensions per aspect (not 1280x720). A still is
    fed as a single frame and zoompan's d= fixes the output frame count exactly.
H1  Audio mixes voice + (optional) ducked music via asplit + sidechaincompress +
    amix so the VOICE IS NEVER DROPPED. With no music the voice is mapped directly.
H3  Every segment is normalized (fps, format=yuv420p, setsar=1) before concat, and
    each clip is forced to exactly its beat duration (-t + tpad/trim) so total video
    duration == audio duration.
C3  The ass= filter path is escaped.
M4  On failure, ffmpeg stderr is folded into the error envelope.
"""
import argparse
import json
import subprocess
from pathlib import Path

from pipeline import result, manifest, assets as pipeline_assets

DIMS = {"9x16": (1080, 1920), "16x9": (1920, 1080)}
CARD_FONTSIZE = {"9x16": 88, "16x9": 64}
CARD_BG = "0x0b1a2a"
# A product still is never rendered full-bleed 1:1 (the *Bill Graham* reduced-size
# lever). It is composited as picture-in-picture on the branded card at this scale.
PIP_SCALE = 0.72
IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# A bold system font for title cards (verified present on the build box).
_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
)


def _font():
    for f in _FONT_CANDIDATES:
        if Path(f).exists():
            return f
    return _FONT_CANDIDATES[0]


def scale_pad_filter(aspect):
    w, h = DIMS[aspect]
    return (f"scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},setsar=1")


def zoompan_clause(duration, aspect, fps=30):
    w, h = DIMS[aspect]
    frames = int(round(duration * fps))
    return (f"zoompan=z='min(zoom+0.0015,1.15)':d={frames}:"
            f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={w}x{h}:fps={fps}")


def _norm(fps):
    return f"fps={fps},format=yuv420p,setsar=1,setpts=PTS-STARTPTS"


def pip_inner_dims(aspect, scale=PIP_SCALE):
    """Even-numbered (w,h) of the picture-in-picture inset for a product still."""
    w, h = DIMS[aspect]
    return (round(w * scale) // 2) * 2, (round(h * scale) // 2) * 2


def _escape_ass_path(path):
    # Escape for use inside a single-quoted ass= filter argument.
    return str(path).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def _segment_input_and_filter(seg, idx, aspect, fps):
    """Return (input_args, filter_chain) for one timeline segment, emitting
    label [v{idx}], normalized and sized to exactly its duration."""
    w, h = DIMS[aspect]
    dur = round(float(seg["duration"]), 3)
    kind = seg["kind"]

    if kind == "card":
        inp = ["-f", "lavfi", "-t", str(dur),
               "-i", f"color=c={CARD_BG}:s={w}x{h}:r={fps}"]
        fs = CARD_FONTSIZE[aspect]
        draw = (f"drawtext=fontfile='{_font()}':textfile='{seg['textfile']}':"
                f"fontcolor=white:fontsize={fs}:line_spacing=14:"
                f"x=(w-text_w)/2:y=(h-text_h)/2")
        chain = f"[{idx}:v]{draw},{_norm(fps)}[v{idx}]"
        return inp, chain

    if kind == "image":
        # Single still frame (no -loop / -t); zoompan d= fixes frame count (C2).
        inp = ["-i", seg["path"]]
        chain = (f"[{idx}:v]scale={w * 2}:-2,{zoompan_clause(dur, aspect, fps)},"
                 f"setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v{idx}]")
        return inp, chain

    if kind == "product":
        # A captured product website still: never full-bleed. Gently Ken-Burns the
        # still INTO a reduced-size PiP inset, then pad it onto the branded card so
        # the final frame is a transformed, reduced-size reproduction (autoplan F2).
        inp = ["-i", seg["path"]]
        iw, ih = pip_inner_dims(aspect)
        frames = int(round(dur * fps))
        chain = (f"[{idx}:v]scale={iw * 2}:-2,"
                 f"zoompan=z='min(zoom+0.0008,1.06)':d={frames}:"
                 f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':s={iw}x{ih}:fps={fps},"
                 f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color={CARD_BG},"
                 f"setsar=1,format=yuv420p,setpts=PTS-STARTPTS[v{idx}]")
        return inp, chain

    # video: trim long clips with -t, clone-pad short clips to exactly dur (H3).
    inp = ["-t", str(dur), "-i", seg["path"]]
    chain = (f"[{idx}:v]{scale_pad_filter(aspect)},"
             f"tpad=stop_mode=clone:stop_duration={dur},trim=duration={dur},"
             f"{_norm(fps)}[v{idx}]")
    return inp, chain


def build_command(segments, music, captions, out_path, aspect, fps=30):
    """Full ffmpeg argv. `segments` is the FULL timeline (cards + beats); each
    carries kind + duration and either a media path or a card text file."""
    if aspect not in DIMS:
        raise ValueError(f"unknown aspect {aspect!r}")
    n = len(segments)
    inputs, filters, concat_parts = [], [], []
    for idx, seg in enumerate(segments):
        inp, chain = _segment_input_and_filter(seg, idx, aspect, fps)
        inputs += inp
        filters.append(chain)
        concat_parts.append(f"[v{idx}]")

    vconcat = "".join(concat_parts) + f"concat=n={n}:v=1:a=0[vbg]"
    cap = f"[vbg]ass='{_escape_ass_path(captions)}'[vout]"

    voice_idx = n
    inputs += ["-i", "audio/voiceover.wav"]
    graph = [*filters, vconcat, cap]
    if music:
        music_idx = voice_idx + 1
        inputs += ["-i", music]
        # asplit the voice: one copy keys the compressor, one is mixed back in,
        # so the voice is NEVER consumed/dropped (H1).
        graph.append(
            f"[{voice_idx}:a]asplit=2[vkey][vmix];"
            f"[{music_idx}:a]volume=0.3[bg];"
            f"[bg][vkey]sidechaincompress=threshold=0.03:ratio=6:"
            f"attack=5:release=300[duck];"
            # normalize=0 keeps the voice at full level (amix's default 1/n scaling
            # would otherwise halve it); music sits ducked underneath.
            f"[duck][vmix]amix=inputs=2:duration=longest:dropout_transition=0:"
            f"normalize=0[aout]")
        amap = "[aout]"
    else:
        # raw input stream specifier -> no brackets (brackets are for filter labels)
        amap = f"{voice_idx}:a"

    fc = ";".join(graph)
    return ["ffmpeg", "-y", *inputs,
            "-filter_complex", fc,
            "-map", "[vout]", "-map", amap,
            "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(fps),
            "-c:a", "aac", "-shortest", "-movflags", "+faststart", out_path]


# --------------------------------------------------------------------------- IO

def _wrap_text(text, width):
    words, lines, cur = text.split(), [], ""
    for word in words:
        if cur and len(cur) + 1 + len(word) > width:
            lines.append(cur)
            cur = word
        else:
            cur = f"{cur} {word}".strip()
    if cur:
        lines.append(cur)
    return "\n".join(lines)


def plan_segments(slug, aspect, script, timings, by_beat):
    """Build the full-timeline segment list and write card text files.
    Hook (id 0) and outro (id -1) become title cards; beats use their asset.

    ``by_beat`` is the reconciled ``{beat_id: asset}`` map (stock b-roll overlaid
    with captured product stills, capture winning) from ``pipeline.assets``."""
    d = manifest.project_dir(slug)
    cards = d / "cards"
    cards.mkdir(exist_ok=True)
    # Floor (autoplan F6): every body beat MUST have an asset before we plan ffmpeg.
    # A capture_failed product beat falls back to its stock b-roll upstream; if even
    # that is missing, fail HERE with the full list, not deep inside ffmpeg planning.
    missing = sorted(t["id"] for t in timings
                     if t["id"] not in (0, -1) and t["id"] not in by_beat)
    if missing:
        raise RuntimeError(
            f"no media asset for beat id(s) {missing}: every body beat needs a "
            f"stock or product asset before stitch (a capture_failed beat must "
            f"fall back to stock b-roll)")
    segments = []
    for t in timings:
        dur = round(t["end"] - t["start"], 3)
        if t["id"] == 0:
            text = script.get("hook", "")
        elif t["id"] == -1:
            text = script.get("outro", "")
        else:
            text = None
        if text is not None:
            tf = cards / f"seg_{t['id']}_{aspect}.txt"
            tf.write_text(_wrap_text(text, 26 if aspect == "9x16" else 42))
            segments.append({"id": t["id"], "kind": "card", "duration": dur,
                             "textfile": str(tf.relative_to(d))})
            continue
        asset = by_beat[t["id"]]  # floor check above guarantees presence
        path = asset["path"]
        is_img = path.lower().endswith(IMG_EXTS)
        if is_img and asset.get("framing") == "pip":
            kind = "product"   # captured product still -> PiP card (never full-bleed)
        elif is_img:
            kind = "image"     # stock photo -> full-bleed Ken Burns
        else:
            kind = "video"
        segments.append({"id": t["id"], "kind": kind, "duration": dur, "path": path})
    return segments


def run_ffmpeg(cmd, cwd):
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-25:])
        raise RuntimeError(f"ffmpeg failed (rc={proc.returncode}):\n{tail}")
    return proc


def _render(slug, force=False, aspects=("16x9",)):
    if manifest.stage_done(slug, "stitch") and not force:
        return result.ok(skipped=True, stage="stitch")
    d = manifest.project_dir(slug)
    script = json.loads((d / "script.json").read_text())
    m = manifest.load(slug)
    timings = m["stages"]["voice"]["beat_timings"]
    media_assets = m["stages"]["media"]["assets"]
    # Reconcile stock b-roll with captured product stills (capture wins per beat).
    # stages.capture is optional: a project with no product captures just uses stock.
    capture_assets = (m["stages"].get("capture") or {}).get("assets", []) or []
    by_beat = pipeline_assets.merge_assets(media_assets, capture_assets)
    music = m["stages"]["media"].get("music")

    outputs = []
    for aspect in aspects:
        segments = plan_segments(slug, aspect, script, timings, by_beat)
        captions = f"captions_{aspect}.ass"
        out_rel = f"out/video_{aspect}.mp4"
        cmd = build_command(segments, music, captions, out_rel, aspect)
        run_ffmpeg(cmd, cwd=d)
        outputs.append(out_rel)
    manifest.set_stage(slug, "stitch", status="done", outputs=outputs)
    return result.ok(outputs=outputs)


def main():
    ap = argparse.ArgumentParser(description="Render the project's video(s)")
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--aspect", choices=["9x16", "16x9", "both"], default="16x9")
    args = ap.parse_args()
    aspects = ("9x16", "16x9") if args.aspect == "both" else (args.aspect,)
    result.run(lambda: _render(args.slug, args.force, aspects), slug=args.slug)


if __name__ == "__main__":
    main()
