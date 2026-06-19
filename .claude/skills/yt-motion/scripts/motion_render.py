"""yt-motion: render brand-locked motion CARDS into the FFmpeg pipeline.

  motion_render.py <slug> --init     # scaffold motion.json (confirmed:false)
  motion_render.py <slug> [--force] [--only <beat>]
  motion_render.py <slug> --doctor

Cards are timeline SEGMENTS, not beat overrides: the outro card (beat -1) swaps
the drawtext outro; a chapter card (beat = chapter start_beat) is a short flash
inserted at the front of that beat. The HyperFrames render is injected (render_fn)
so the gate/fit/cache/retry/fallback are unit-tested without Docker."""
import hashlib
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))  # make `pipeline` importable

ERR_NO_PLAN = "motion_no_plan"
ERR_INVALID_PLAN = "motion_invalid_plan"
ERR_UNCONFIRMED = "motion_unconfirmed"
ERR_NO_TIMINGS = "motion_no_timings"
ERR_MISSING_DOCKER = "motion_missing_docker"
ERR_MISSING_NODE = "motion_missing_node"
ERR_MISSING_HF = "motion_missing_hf"
ERR_UNFITTABLE = "motion_unfittable"
ERR_RENDER_FAILED = "motion_render_failed"

_INSTALL = {
    "docker": "install Docker Engine then `sudo systemctl enable --now docker`",
    "node": "install Node 22+ resolvable in non-interactive shells",
    "hyperframes": "install the HyperFrames CLI (`npm i -g hyperframes`)",
}


class MotionError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def doctor(which=shutil.which):
    missing = [t for t in ("docker", "node", "hyperframes") if which(t) is None]
    if not missing:
        return {"ok": True, "missing": [], "next_action": ""}
    fixes = "; ".join(_INSTALL[t] for t in missing)
    return {"ok": False, "missing": missing,
            "next_action": f"{fixes}. Or skip motion and keep stock b-roll "
                           f"(motion is optional)."}


def comp_key(item, duration, template_bytes, tokens_bytes, engine_version):
    """Cache key over the RESOLVED composition: template name+content, data,
    lottie, duration, brand tokens, AND engine_version. Editing the HTML/tokens
    or bumping the pinned engine re-renders (and flips the stitch-change diff)."""
    h = hashlib.sha256()
    h.update(json.dumps({
        "template": item.get("template"),
        "data": item.get("data"),
        "lottie": item.get("lottie"),
        "duration": round(float(duration), 3),
        "engine": engine_version,
    }, sort_keys=True).encode())
    h.update(template_bytes or b"")
    h.update(tokens_bytes or b"")
    return h.hexdigest()


from pipeline import manifest, result, schema  # noqa: E402
import brand  # noqa: E402


def _load_script(slug, root):
    return json.loads((manifest.project_dir(slug, root) / "script.json").read_text())


def card_positions(script):
    # Only positions _render can actually place: chapter starts + the outro.
    # (Hook id 0 is excluded by policy; a non-chapter body beat is unplaceable
    # and validation rejects it up front rather than dropping it at render.)
    return {ch["start_beat"] for ch in script.get("chapters", [])} | {-1}


def proposed_motion_json(script):
    out = [{"beat": ch["start_beat"], "kind": "card", "template": "card/chapter",
            "data": {"title": ch.get("title")}, "confirmed": False}
           for ch in script.get("chapters", [])]
    out.append({"beat": -1, "kind": "card", "template": "card/outro",
                "data": {"title": script.get("title")}, "confirmed": False})
    return out


def _init(slug, root="project"):
    script = _load_script(slug, root)
    d = manifest.project_dir(slug, root)
    (d / "motion.json").write_text(json.dumps(proposed_motion_json(script), indent=2))
    brand.generate(slug, root)
    return result.ok(stage="motion",
                     next_action=f"review {d / 'motion.json'}, set confirmed:true, "
                                 f"then run motion_render.py {slug}")


def validate_plan(slug, root="project"):
    script = _load_script(slug, root)
    pj = manifest.project_dir(slug, root) / "motion.json"
    motion = json.loads(pj.read_text()) if pj.exists() else None
    return schema.validate_motion(motion, card_positions(script))


from pipeline import motion_fit, video_spec  # noqa: E402

COMP_MIN_S = 2.0       # fixed intro+outro of a card comp
MOTION_CARD_SEC = 3.0  # chapter flash length
MIN_FOOTAGE_S = 2.0    # footage that must remain after a chapter flash
MAX_CARD_S = 8.0       # ceiling before a card is treated as a planning error

_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def partition_confirmed(items):
    confirmed = [i for i in items if i.get("confirmed") is True]
    return confirmed, [i for i in items if i.get("confirmed") is not True]


def _durations(slug, root):
    try:
        v = manifest.load(slug, root)["stages"].get("voice", {})
    except FileNotFoundError:
        return {}
    return {t["id"]: round(t["end"] - t["start"], 3) for t in v.get("beat_timings", [])}


def _template_bytes(item):
    p = _TEMPLATES / f"{item['template']}.html"
    return p.read_bytes() if p.exists() else b""


def _render_with_retries(render_fn, item, dur, out_path, attempts):
    last = None
    for _ in range(max(attempts, 1)):
        try:
            render_fn(item, dur, out_path)
            return
        except Exception as exc:  # noqa: BLE001
            last = exc
    raise last


def _render(slug, force=False, only=None, render_fn=None, engine_version="unset",
            attempts=2, root="project"):
    if manifest.stage_done(slug, "motion") and not force and only is None:
        return result.ok(stage="motion", skipped="already done")
    errs = validate_plan(slug, root)
    if errs:
        return result.err("invalid motion.json", error_code=ERR_INVALID_PLAN, errors=errs)

    durations = _durations(slug, root)
    if not durations:
        return result.err("no beat_timings — run yt-voice first",
                          error_code=ERR_NO_TIMINGS,
                          next_action="run yt-voice, then yt-motion")

    d = manifest.project_dir(slug, root)
    items = json.loads((d / "motion.json").read_text())
    confirmed, _ = partition_confirmed(items)
    if only is not None:
        confirmed = [i for i in confirmed if i["beat"] == only]
    if not confirmed:
        return result.err("no confirmed motion items", error_code=ERR_UNCONFIRMED,
                          next_action="set confirmed:true in motion.json")

    script = _load_script(slug, root)
    chapter_starts = {ch["start_beat"] for ch in script.get("chapters", [])}
    tokens_bytes = (d / "motion" / "tokens.css").read_bytes() \
        if (d / "motion" / "tokens.css").exists() else b""
    prior = {a["beat"]: a for a in
             (manifest.load(slug, root)["stages"].get("motion") or {}).get("assets", [])}

    assets, warnings = [], []
    for item in confirmed:
        beat = item["beat"]
        if beat == -1:
            hold, warn = motion_fit.outro_hold(COMP_MIN_S, durations.get(-1, 0.0), MAX_CARD_S)
            rdur = round(COMP_MIN_S + hold, 3)   # == outro_s; fills the full window
            if warn:
                warnings.append({"beat": beat, "code": "motion_card_long",
                                 "next_action": f"outro longer than {MAX_CARD_S}s — "
                                                f"sanity-check the card; rendering full length"})
        elif beat in chapter_starts:
            if not motion_fit.chapter_fits(durations.get(beat, 0.0), MOTION_CARD_SEC, MIN_FOOTAGE_S):
                warnings.append({"beat": beat, "code": ERR_UNFITTABLE,
                                 "next_action": "beat too short for a chapter flash; keeps b-roll"})
                continue
            rdur = MOTION_CARD_SEC
        else:  # not a placeable card position (schema should have caught it)
            warnings.append({"beat": beat, "code": ERR_INVALID_PLAN,
                             "next_action": "not a chapter start or outro"})
            continue

        key = comp_key(item, rdur, _template_bytes(item), tokens_bytes, engine_version)
        cached = prior.get(beat)
        out_path = f"media/motion_card_{beat}.mp4"
        if not force and cached and cached.get("comp_key") == key and (d / out_path).exists():
            assets.append(cached)
            continue
        try:
            _render_with_retries(render_fn, item, rdur, out_path, attempts)
        except Exception as exc:  # noqa: BLE001
            warnings.append({"beat": beat, "code": ERR_RENDER_FAILED, "detail": str(exc),
                             "next_action": "keeps b-roll/drawtext; fix template and --force"})
            continue
        assets.append({"beat": beat, "kind": "card", "path": out_path, "duration": rdur,
                       "comp_key": key, "source": "hyperframes"})

    changed = ({(a["beat"], a.get("comp_key")) for a in assets}
               != {(a["beat"], a.get("comp_key")) for a in prior.values()})
    manifest.set_stage(slug, "motion", status="done", engine="hyperframes",
                       engine_version=engine_version, assets=assets)
    if changed:
        manifest.set_stage(slug, "stitch", status="pending")
    return result.ok(stage="motion", rendered=len(assets), assets=assets,
                     warnings=warnings, stitch_invalidated=changed)


def _resolve_engine_version():  # pragma: no cover - integration
    """Resolve the pinned HyperFrames Docker image digest. Wired in Task 11."""
    return "unset"


def _docker_render(item, duration, out_path):  # pragma: no cover - integration
    """Drive HyperFrames in Docker to render `item` to `out_path` at `duration`
    seconds, muted+silent-track, video_spec size/fps/pixfmt, color/range tagged."""
    raise NotImplementedError("wired in Task 11 / Phase-0 spike")


def _timings_present(slug, root="project"):
    return bool(_durations(slug, root))


def main(argv=None):
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("slug")
    p.add_argument("--init", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--only", type=int, default=None)
    p.add_argument("--doctor", action="store_true")
    a = p.parse_args(argv)
    if a.doctor:
        d = doctor()
        env = result.ok(**d) if d["ok"] else result.err(d["next_action"], **d)
        result.run(lambda: env, a.slug)
        return 0 if d["ok"] else 1
    if a.init:
        result.run(lambda: _init(a.slug), a.slug)
        return 0
    r = result.run(lambda: _render(a.slug, force=a.force, only=a.only,
                                   render_fn=_docker_render,
                                   engine_version=_resolve_engine_version()), a.slug)
    return 0 if r.get("success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
