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
