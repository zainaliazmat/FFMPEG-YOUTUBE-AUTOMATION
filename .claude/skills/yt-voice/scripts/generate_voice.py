"""yt-voice — Kokoro-82M TTS per beat (CPU).

Reads project/<slug>/script.json, synthesizes hook + each beat narration + outro
in order, concatenates to one 24kHz WAV, and records per-segment beat_timings into
manifest.json.

Fix #4: a SINGLE locked channel voice with a MATCHING lang_code. The plan's
rotation allowlist mixed American (af_/am_) and British (bf_) voices while
lang_code was hardcoded to 'a'. We lock one voice whose accent prefix == LANG_CODE
and leave pick_voice() as the clean seam where rotation slots in later.
"""
import argparse

from pipeline import result, manifest, schema

# American-English female voice; first letter 'a' == American accent == LANG.
VOICE = "af_heart"
LANG = "a"
SR = 24000


def pick_voice(slug, override=None):
    """The rotation seam. Phase 1: always the one locked channel voice unless an
    explicit override is passed. Later phases can rotate here (keeping accent
    consistent with LANG)."""
    if override:
        return override
    return VOICE


def plan_beats(script):
    """Ordered synthesis plan. Hook is id 0, outro is id -1 (so stitch can render
    title cards for them); beats keep their real ids. Skips empty text."""
    items = []
    if script.get("hook"):
        items.append({"id": 0, "text": script["hook"]})
    for beat in script.get("beats", []):
        if beat.get("narration"):
            items.append({"id": beat["id"], "text": beat["narration"]})
    if script.get("outro"):
        items.append({"id": -1, "text": script["outro"]})
    return items


def concat_timings(durations, ids=None):
    """Cumulative [{id,start,end}]. ids defaults to positional indices; pass the
    plan ids so timings carry real beat ids for stitch's asset lookup."""
    out, t = [], 0.0
    for i, d in enumerate(durations):
        seg_id = ids[i] if ids is not None else i
        out.append({"id": seg_id, "start": round(t, 3), "end": round(t + d, 3)})
        t += d
    return out


def _synthesize(slug, force=False, voice_override=None):
    import json
    import numpy as np
    import soundfile as sf
    from kokoro import KPipeline

    d = manifest.project_dir(slug)
    script = json.loads((d / "script.json").read_text())
    errs = schema.validate_script(script)
    if errs:
        return result.err("invalid script.json: " + "; ".join(errs))
    if manifest.stage_done(slug, "voice") and not force:
        return result.ok(skipped=True, stage="voice")

    plan = plan_beats(script)
    voice = pick_voice(slug, voice_override)
    pipe = KPipeline(lang_code=LANG)
    chunks, durations = [], []
    for item in plan:
        audio = np.concatenate([g.audio for g in pipe(item["text"], voice=voice)])
        chunks.append(audio)
        durations.append(len(audio) / SR)
    full = np.concatenate(chunks)
    out_path = d / "audio" / "voiceover.wav"
    sf.write(out_path, full, SR)

    timings = concat_timings(durations, ids=[p["id"] for p in plan])
    manifest.set_stage(slug, "voice", status="done",
                       artifact="audio/voiceover.wav", beat_timings=timings,
                       voice=voice)
    return result.ok(artifact=str(out_path), beats=len(plan), voice=voice,
                     duration=round(sum(durations), 3))


def main():
    ap = argparse.ArgumentParser(description="Generate voiceover for a project slug")
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--voice", default=None, help="override the locked channel voice")
    args = ap.parse_args()
    result.run(lambda: _synthesize(args.slug, args.force, args.voice), slug=args.slug)


if __name__ == "__main__":
    main()
