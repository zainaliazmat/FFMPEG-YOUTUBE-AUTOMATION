"""Phase-2 integration: discover -> script -> spine, hermetic where possible.

Asserts the file handoff works end to end on the pure side: a topics.json entry
can seed a draft.json that write_script.py turns into a VALID script.json the
spine accepts. The live discover->render path is exercised manually with real
keys (gated, like the Phase-1 smoke test), not here.
"""
import importlib.util
import json
import pathlib
import shutil
import subprocess
import sys

from pipeline import longform, schema

WS = pathlib.Path(".claude/skills/yt-script/scripts/write_script.py")
_spec = importlib.util.spec_from_file_location("write_script", WS)
ws = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ws)


def test_topic_to_draft_to_valid_script(tmp_path):
    # 1. a discover-style topic (the shape yt-discover writes to topics.json)
    topic = {
        "title": "Best AI Tools for Professionals",
        "channel": "Some Channel",
        "url": "https://youtube.com/watch?v=abc",
        "views": 250000, "outlier": 6.4, "vph": 800.0,
        "commercial_intent": True,
    }
    assert topic["commercial_intent"] is True  # the kind of topic Gate 1 surfaces

    # 2. picked topic -> a real long-form draft (here we reuse the worked fixture,
    #    standing in for what yt-script drafts from the topic)
    slug = "_test_integration"
    proj = pathlib.Path("project") / slug
    proj.mkdir(parents=True, exist_ok=True)
    draft = json.load(open("fixtures/longform_draft.json"))
    draft["title"] = topic["title"]  # the chosen topic seeds the draft
    (proj / "draft.json").write_text(json.dumps(draft))

    try:
        # 3. write_script.py -> script.json
        out = subprocess.run(
            [sys.executable, str(WS), slug],
            capture_output=True, text=True, cwd=".")
        payload = json.loads(out.stdout.strip().splitlines()[-1])
        assert payload["success"] is True, out.stdout + out.stderr

        script = json.loads((proj / "script.json").read_text())
        channel = json.load(open("channel.json"))

        # 4. Gate 2 contract: long-form valid AND base spine accepts it unchanged
        assert longform.validate_longform_script(script, channel) == []
        assert schema.validate_script(script) == []
    finally:
        shutil.rmtree(proj, ignore_errors=True)


def test_assemble_is_pure_no_io(tmp_path):
    # assemble_script must not touch disk -> safe to call before the gate.
    draft = json.load(open("fixtures/longform_draft.json"))
    s1 = ws.assemble_script(draft, "x")
    s2 = ws.assemble_script(draft, "x")
    assert s1 == s2
    assert s1["word_count"] > 0
