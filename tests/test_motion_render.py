import motion_render as mr


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
