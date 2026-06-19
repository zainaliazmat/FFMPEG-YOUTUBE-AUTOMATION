import json
from pipeline import manifest
import motion_render as mr


def _script(d):
    (d / "script.json").write_text(json.dumps({
        "slug": "proj", "title": "Best AI tools", "hook": "h", "outro": "o", "cta": "c",
        "chapters": [{"title": "Pricing", "start_beat": 8}],
        "beats": [{"id": 8, "narration": "n", "b_roll_keywords": ["x"]}],
    }))


def test_doctor_flags_missing_docker_with_next_action():
    def which(tool):
        return None if tool == "docker" else f"/usr/bin/{tool}"
    r = mr.doctor(which=which)
    assert r["ok"] is False and "docker" in r["missing"]
    assert "skip motion" in r["next_action"].lower()


def test_doctor_ok_when_all_present():
    r = mr.doctor(which=lambda t: f"/usr/bin/{t}")
    assert r["ok"] is True and r["missing"] == []


def test_comp_key_changes_with_template_tokens_duration_and_engine():
    item = {"template": "card/chapter", "data": {"title": "X"}, "lottie": None}
    html, tok, eng = b"<html>v1</html>", b":root{--bg:#0b1a2a}", "hf@sha256:aaa"
    base = mr.comp_key(item, 3.0, html, tok, eng)
    assert base == mr.comp_key(item, 3.0, html, tok, eng)
    assert base != mr.comp_key(item, 3.0, b"<html>v2</html>", tok, eng)   # html edit
    assert base != mr.comp_key(item, 5.0, html, tok, eng)                 # duration
    assert base != mr.comp_key(item, 3.0, html, b":root{--bg:#000}", eng) # tokens edit
    assert base != mr.comp_key(item, 3.0, html, tok, "hf@sha256:bbb")     # engine bump


def test_init_scaffolds_chapter_and_outro_unconfirmed(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = manifest.project_dir("proj")
    _script(d)
    r = mr._init("proj")
    assert r["success"] is True
    m = json.loads((d / "motion.json").read_text())
    beats = {item["beat"] for item in m}
    assert beats == {8, -1}                          # chapter start + outro, no hook
    assert all(item["confirmed"] is False for item in m)
    assert next(i for i in m if i["beat"] == 8)["data"]["title"] == "Pricing"


def test_validate_plan_flags_bad_beat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = manifest.project_dir("proj")
    _script(d)
    (d / "motion.json").write_text(json.dumps(
        [{"beat": 999, "kind": "card", "template": "card/chapter", "confirmed": True}]))
    errs = mr.validate_plan("proj")
    assert any("999" in e for e in errs)
