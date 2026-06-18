"""yt-script writer tests — the deterministic parts (creative gen is gated, not unit-tested)."""
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys

SCRIPT = pathlib.Path(".claude/skills/yt-script/scripts/write_script.py")
spec = importlib.util.spec_from_file_location("write_script", SCRIPT)
ws = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ws)


def test_assemble_computes_word_count_and_duration():
    draft = {
        "title": "T",
        "hook": "one two three",          # 3
        "outro": "four five",             # 2
        "beats": [
            {"id": 1, "narration": "six seven eight", "b_roll_keywords": ["k"]},   # 3
            {"id": 2, "narration": "nine ten", "b_roll_keywords": ["k"]},          # 2
        ],
    }
    script = ws.assemble_script(draft, "demo-slug")
    assert script["slug"] == "demo-slug"
    assert script["word_count"] == 10
    # 10 words / 140 wpm
    assert script["estimated_duration_min"] == round(10 / 140, 2)


def test_assemble_honors_draft_wpm():
    draft = {"hook": "a b c d e f g", "outro": "", "beats": [], "wpm": 7}
    script = ws.assemble_script(draft, "s")
    assert script["estimated_duration_min"] == 1.0  # 7 words / 7 wpm


def test_review_summary_includes_title_duration_and_every_source():
    script = json.load(open("fixtures/longform_script.json"))
    summary = ws.review_summary(script)
    assert script["title"] in summary
    assert str(script["estimated_duration_min"]) in summary
    for s in script["sources"]:
        assert s["claim"] in summary


def test_cli_rejects_noncompliant_draft(tmp_path, monkeypatch):
    # A draft missing chapters/midroll/sources/pov + too-short -> rejected with errors.
    slug = "_test_ws_reject"
    proj = pathlib.Path("project") / slug
    proj.mkdir(parents=True, exist_ok=True)
    (proj / "draft.json").write_text(json.dumps({
        "title": "Too thin",
        "hook": "short hook here",
        "outro": "short outro",
        "beats": [{"id": 1, "narration": "a b c", "b_roll_keywords": ["k"]}],
        "cta": "sub",
    }))
    try:
        out = subprocess.run(
            [sys.executable, str(SCRIPT), slug],
            capture_output=True, text=True, cwd=".")
        payload = json.loads(out.stdout.strip().splitlines()[-1])
        assert payload["success"] is False
        assert "errors" in payload and payload["errors"]
        # script.json must NOT be written for a non-compliant draft
        assert not (proj / "script.json").exists()
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_cli_accepts_compliant_draft():
    slug = "_test_ws_accept"
    proj = pathlib.Path("project") / slug
    proj.mkdir(parents=True, exist_ok=True)
    # Use the real 31-beat draft: its actual word count lands in the 8-20 min
    # range, so the CLI's recomputed duration passes validation.
    draft = json.load(open("fixtures/longform_draft.json"))
    (proj / "draft.json").write_text(json.dumps(draft))
    try:
        out = subprocess.run(
            [sys.executable, str(SCRIPT), slug],
            capture_output=True, text=True, cwd=".")
        payload = json.loads(out.stdout.strip().splitlines()[-1])
        assert payload["success"] is True, out.stdout + out.stderr
        assert payload["artifact"] == "script.json"
        assert (proj / "script.json").exists()
        written = json.loads((proj / "script.json").read_text())
        assert written["slug"] == slug
        assert "word_count" in written and "estimated_duration_min" in written
    finally:
        shutil.rmtree(proj, ignore_errors=True)
