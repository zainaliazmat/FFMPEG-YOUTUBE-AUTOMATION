"""yt-script assembler: turn Claude's drafted content into a validated script.json.

The creative work (research, synthesis, writing) happens in SKILL.md behind a
human approval gate. THIS file is the deterministic, tested part: it computes
word_count + estimated_duration_min, validates the draft against the long-form
contract, writes script.json, initializes the manifest, and prints a review
summary for the approval gate. It never auto-proceeds to rendering.

CLI:  python write_script.py <slug>
  reads  project/<slug>/draft.json
  writes project/<slug>/script.json   (only if the draft is long-form-compliant)
"""
import json
import sys
from pathlib import Path

# Allow running as a loose script (skills are invoked by path, not installed).
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pipeline import longform, manifest, result  # noqa: E402


def assemble_script(draft, slug):
    """Merge slug + computed word_count/estimated_duration_min into the draft."""
    script = {**draft, "slug": slug}
    wc = longform.word_count(script)
    script["word_count"] = wc
    script["estimated_duration_min"] = longform.estimate_duration_min(
        wc, draft.get("wpm", 140))
    return script


def review_summary(script):
    """Human-readable summary for the approval gate."""
    chs = "\n".join(
        f"  - {c.get('title')} (beat {c.get('start_beat')})"
        for c in script.get("chapters", [])) or "  (none)"
    srcs = "\n".join(
        f"  - {s.get('claim')} -> {s.get('source')} {s.get('url', '')}"
        f"{'' if s.get('verified') else '  [UNVERIFIED]'}"
        for s in script.get("sources", [])) or "  (none)"
    return (
        f"TITLE: {script.get('title')}\n"
        f"POV: {script.get('channel_pov')}\n"
        f"~{script.get('estimated_duration_min')} min, "
        f"{len(script.get('beats', []))} beats, "
        f"{len(script.get('sources', []))} sources\n"
        f"CHAPTERS:\n{chs}\n"
        f"SOURCES:\n{srcs}"
    )


def _run(slug):
    d = manifest.project_dir(slug)
    draft_path = d / "draft.json"
    if not draft_path.is_file():
        return result.err(f"no draft at {draft_path}")
    draft = json.loads(draft_path.read_text())
    channel = json.loads(Path("channel.json").read_text())

    script = assemble_script(draft, slug)
    errs = longform.validate_longform_script(script, channel)
    if errs:
        return result.err(
            "draft not long-form-compliant: " + "; ".join(errs), errors=errs)

    (d / "script.json").write_text(json.dumps(script, indent=2))
    manifest.init(slug)
    return result.ok(
        artifact="script.json",
        summary=review_summary(script),
        duration_min=script["estimated_duration_min"],
        word_count=script["word_count"],
    )


if __name__ == "__main__":
    if len(sys.argv) < 2:
        result.run(lambda: result.err("usage: write_script.py <slug>"))
        sys.exit(1)
    slug = sys.argv[1]
    result.run(lambda: _run(slug), slug=slug)
