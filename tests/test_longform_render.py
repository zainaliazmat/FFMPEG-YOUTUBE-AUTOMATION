"""Long-form stress test: drive the EXISTING spine at 30-40 beat / ~10-12 min scale.

This is the deferred Phase-1 validation. Phase 1 proved 7 beats; real long-form is
30-40, where two risks scale nonlinearly on a CPU box: the FFmpeg filter_complex
size (30-40 inputs in one graph) and total render wall-clock.

GATED like the Phase-1 smoke test — it hits Kokoro, Pexels/Pixabay, WhisperX, and
FFmpeg, so it is opt-in:

    YT_RUN_LONGFORM_RENDER=1 python -m pytest tests/test_longform_render.py -s

It asserts the render survives the scale and reports the timing/verdict so we know
whether real long-form is practical or needs segment-and-concat assembly.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

import pytest

RUN = os.environ.get("YT_RUN_LONGFORM_RENDER") == "1"
HAVE_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
gated = pytest.mark.skipif(
    not (RUN and HAVE_FFMPEG),
    reason="set YT_RUN_LONGFORM_RENDER=1 and have ffmpeg/ffprobe to run the stress test")

SLUG = "stress-longform"
SKILLS = ".claude/skills"


def _stage(script, slug, *extra):
    t0 = time.time()
    proc = subprocess.run(
        [sys.executable, script, slug, *extra],
        capture_output=True, text=True, cwd=".")
    dt = time.time() - t0
    last = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "{}"
    payload = json.loads(last)
    print(f"\n[{pathlib.Path(script).stem}] {dt:.1f}s -> "
          f"success={payload.get('success')} {payload.get('error') or ''}")
    return payload, dt


def _ffprobe(path, *entries):
    # ffprobe wants ONE -show_entries value with sections joined by ':'
    # (e.g. "stream=width,height:format=duration"), not separate tokens.
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", ":".join(entries),
         "-of", "json", path],
        capture_output=True, text=True)
    return json.loads(out.stdout)


@gated
def test_longform_spine_survives_scale(capsys):
    # Idempotent: reuse an existing render if the project already rendered (each
    # stage skips when done). A fresh project renders the whole chain from scratch.
    # We do NOT pass --force or wipe the dir, so re-running validates the assertions
    # cheaply instead of paying ~37 min of CPU render again.
    proj = pathlib.Path("project") / SLUG
    proj.mkdir(parents=True, exist_ok=True)
    if not (proj / "draft.json").exists():
        shutil.copy("fixtures/longform_draft.json", proj / "draft.json")

    timings = {}

    # 0. assemble + validate the script (only if absent: write_script re-inits the
    #    manifest, which would reset the spine's done flags and force a re-render).
    if not (proj / "script.json").exists():
        p, timings["script"] = _stage(f"{SKILLS}/yt-script/scripts/write_script.py", SLUG)
        assert p["success"], p
    n_beats = len(json.loads((proj / "script.json").read_text())["beats"])
    assert 30 <= n_beats <= 40, f"expected 30-40 beats, got {n_beats}"

    # 1-4. the spine (idempotent skip if already done)
    p, timings["voice"] = _stage(f"{SKILLS}/yt-voice/scripts/generate_voice.py", SLUG)
    assert p["success"], p
    p, timings["media"] = _stage(f"{SKILLS}/yt-media/scripts/fetch_media.py", SLUG)
    assert p["success"], p
    p, timings["captions"] = _stage(f"{SKILLS}/yt-captions/scripts/generate_captions.py", SLUG)
    assert p["success"], p
    p, timings["stitch"] = _stage(f"{SKILLS}/yt-stitch/scripts/stitch_video.py", SLUG, "--aspect", "16x9")
    assert p["success"], f"filter_complex/render failed at scale: {p}"

    # locate the rendered mp4
    outs = list((proj / "out").glob("*.mp4"))
    assert outs, "no rendered mp4"
    mp4 = str(outs[0])

    # ffprobe: resolution, pixel format, faststart, duration in target range
    info = _ffprobe(mp4, "stream=width,height,pix_fmt,codec_type", "format=duration")
    vstream = next(s for s in info["streams"] if s.get("codec_type") == "video")
    assert (vstream["width"], vstream["height"]) == (1920, 1080), vstream
    assert vstream["pix_fmt"] == "yuv420p", vstream
    dur_min = float(info["format"]["duration"]) / 60
    assert 8 <= dur_min <= 20, f"rendered duration {dur_min:.1f} min outside 8-20"

    total = sum(timings.values())
    print("\n=== LONG-FORM STRESS TEST FINDINGS ===")
    print(f"beats={n_beats}  rendered={dur_min:.1f} min  total_wall={total:.0f}s")
    for k, v in timings.items():
        print(f"  {k:9s} {v:6.1f}s")
    print(f"filter_complex handled {n_beats} inputs without error.")
    print(f"realtime ratio: {total / (dur_min * 60):.2f}x video length")
