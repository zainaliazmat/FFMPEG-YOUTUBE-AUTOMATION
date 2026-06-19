import json
from pathlib import Path
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


def _confirm(d, items):
    (d / "motion.json").write_text(json.dumps(items))


def _voice_done(slug, timings):
    manifest.set_stage(slug, "voice", status="done",
                       beat_timings=[{"id": k, "start": 0.0, "end": v}
                                     for k, v in timings.items()])


def _templates_present():
    base = Path(__file__).resolve().parent.parent / ".claude/skills/yt-motion/templates/card"
    base.mkdir(parents=True, exist_ok=True)
    for n in ("chapter.html", "outro.html"):
        p = base / n
        if not p.exists():
            p.write_text("<html><body><h1></h1></body></html>")


def test_render_requires_voice_timings(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    r = mr._render("proj", render_fn=lambda *a: None)
    assert r["success"] is False and r["error_code"] == mr.ERR_NO_TIMINGS


def test_render_refuses_unconfirmed_stays_pending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    mr._init("proj")  # all confirmed:false
    r = mr._render("proj", render_fn=lambda *a: None)
    assert r["success"] is False and r["error_code"] == mr.ERR_UNCONFIRMED
    assert manifest.stage_done("proj", "motion") is False


def test_render_outro_card_uses_injected_renderer_and_persists_engine_version(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    manifest.set_stage("proj", "stitch", status="done")
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    calls = []
    def fake(item, dur, out_path):
        calls.append((item["beat"], dur)); (d / out_path).write_bytes(b"\x00")
    r = mr._render("proj", render_fn=fake, engine_version="hf@sha256:abc")
    assert r["success"] is True and r["rendered"] == 1
    assert calls == [(-1, 6.0)]                       # outro fills its 6s segment
    assert manifest.load("proj")["stages"]["motion"]["engine_version"] == "hf@sha256:abc"
    assert manifest.stage_done("proj", "stitch") is False   # invalidated (changed)


def test_render_long_outro_fills_full_window_not_clamped(tmp_path, monkeypatch):
    # Bug-1 regression: a 15s outro must render a 15s MP4 (== the stitch segment),
    # not an 8s clamp that would freeze for 7s.
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 15.0})
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    seen = []
    def fake(item, dur, out_path):
        seen.append(dur); (d / out_path).write_bytes(b"\x00")
    r = mr._render("proj", render_fn=fake)
    assert seen == [15.0]                              # full window, not 8.0
    assert r["assets"][0]["duration"] == 15.0
    assert any(w["code"] == "motion_card_long" for w in r["warnings"])


def test_render_chapter_too_short_skips_to_broll(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 4.0, -1: 6.0})            # beat 8 too short for 3s flash + footage
    _confirm(d, [{"beat": 8, "kind": "card", "template": "card/chapter",
                  "data": {"title": "Pricing"}, "confirmed": True}])
    r = mr._render("proj", render_fn=lambda *a: None)
    assert r["success"] is True and r["rendered"] == 0
    assert any(w["code"] == mr.ERR_UNFITTABLE for w in r["warnings"])


def test_render_retries_then_falls_back_to_broll(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    n = {"c": 0}
    def boom(*a):
        n["c"] += 1; raise RuntimeError("chrome crashed")
    r = mr._render("proj", render_fn=boom, attempts=2)
    assert n["c"] == 2                                 # retried before giving up
    assert r["success"] is True and r["assets"] == []
    assert any(w["code"] == mr.ERR_RENDER_FAILED for w in r["warnings"])


def test_normal_run_skips_unchanged_but_force_rerenders(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    _confirm(d, [{"beat": -1, "kind": "card", "template": "card/outro",
                  "data": {"title": "t"}, "confirmed": True}])
    n = {"c": 0}
    def fake(item, dur, out_path):
        n["c"] += 1; (d / out_path).write_bytes(b"\x00")
    mr._render("proj", render_fn=fake)
    mr._render("proj", force=False, render_fn=fake)   # unchanged -> cached
    assert n["c"] == 1
    mr._render("proj", force=True, render_fn=fake)    # force -> re-render
    assert n["c"] == 2


def test_only_renders_single_beat(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path); _templates_present()
    d = manifest.project_dir("proj"); _script(d)
    _voice_done("proj", {8: 11.0, -1: 6.0})
    _confirm(d, [
        {"beat": 8, "kind": "card", "template": "card/chapter", "data": {"title": "P"}, "confirmed": True},
        {"beat": -1, "kind": "card", "template": "card/outro", "data": {"title": "t"}, "confirmed": True}])
    rendered = []
    mr._render("proj", force=True, only=-1,
               render_fn=lambda i, dur, o: (rendered.append(i["beat"]),
                                            (d / o).write_bytes(b"\x00")))
    assert rendered == [-1]


def test_doctor_cli_exits_nonzero_when_missing(monkeypatch, capsys):
    monkeypatch.setattr(mr.shutil, "which", lambda t: None)  # everything missing
    rc = mr.main(["proj", "--doctor"])
    assert rc != 0
