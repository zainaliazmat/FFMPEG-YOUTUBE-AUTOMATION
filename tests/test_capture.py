import importlib.util
import json
import pathlib

import pytest

from pipeline import schema

spec = importlib.util.spec_from_file_location(
    "capture_sites",
    pathlib.Path(".claude/skills/yt-capture/scripts/capture_sites.py"))
cap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cap)

PNG_SIG = b"\x89PNG\r\n\x1a\n"


# --------------------------------------------------------- products validator

def test_validate_products_none_is_valid():
    assert schema.validate_products(None, [1, 2, 3]) == []


def test_validate_products_good():
    p = [{"name": "Granola", "beats": [4, 5]}]
    assert schema.validate_products(p, [4, 5, 6]) == []


def test_validate_products_rejects_unknown_beat_and_empty_name():
    p = [{"name": "", "beats": [99]}]
    errs = schema.validate_products(p, [4, 5])
    assert any("name" in e for e in errs)
    assert any("not a body beat" in e for e in errs)


def test_validate_products_rejects_card_ids():
    # card ids (0/-1) are not positive body-beat ids -> rejected
    assert schema.validate_products([{"name": "X", "beats": [0]}], [4, 5])
    assert schema.validate_products([{"name": "X", "beats": [-1]}], [4, 5])


# ------------------------------------------------------------- extraction

def test_extract_prefers_declared_products():
    script = {"products": [{"name": "Granola", "beats": [4, 5]}],
              "beats": [{"id": 4, "narration": "Otter is great"}]}
    assert cap.extract_products(script) == [{"name": "Granola", "beats": [4, 5]}]


def test_proper_noun_fallback_maps_names_to_beats():
    script = {"beats": [
        {"id": 4, "narration": "First up, Granola. The best note taker."},
        {"id": 5, "narration": "Then Otter joins the call."},
    ]}
    prods = cap.extract_products(script)
    names = {p["name"]: p["beats"] for p in prods}
    assert "Granola" in names and names["Granola"] == [4]
    assert "Otter" in names and names["Otter"] == [5]
    # stopword-led phrases are not products
    assert "First" not in names and "The" not in names and "Then" not in names


def test_proposed_products_json_is_unconfirmed_with_all_fields():
    pj = cap.proposed_products_json([{"name": "Granola", "beats": [4]}])
    e = pj[0]
    assert e["confirmed"] is False
    assert set(e) == {"name", "url", "pages", "press_kit", "image", "beats", "confirmed"}
    assert e["url"].startswith("https://")


# ------------------------------------------------------------- resolution

def test_resolve_source_precedence():
    assert cap.resolve_source({"image": "x.png", "press_kit": "u", "url": "v"})[0] == "image"
    assert cap.resolve_source({"press_kit": "u", "url": "v"})[0] == "press_kit"
    assert cap.resolve_source({"url": "v"}) == ("playwright", ["v"])
    assert cap.resolve_source({"pages": ["a", "b"]}) == ("playwright", ["a", "b"])
    assert cap.resolve_source({"name": "x"})[0] == "none"


def test_partition_confirmed():
    prods = [{"name": "a", "confirmed": True}, {"name": "b", "confirmed": False},
             {"name": "c"}]
    confirmed, unconfirmed = cap.partition_confirmed(prods)
    assert [p["name"] for p in confirmed] == ["a"]
    assert [p["name"] for p in unconfirmed] == ["b", "c"]


# ------------------------------------------------------------- capture_one

def test_capture_one_local_image(tmp_path):
    img = tmp_path / "hand.png"
    img.write_bytes(PNG_SIG + b"junk")
    (tmp_path / "media").mkdir()
    asset = cap.capture_one(
        {"name": "Granola", "beats": [4, 5], "image": str(img)},
        tmp_path / "media", tmp_path)
    assert asset["framing"] == "pip"
    assert asset["beats"] == [4, 5]
    assert asset["source"] == "image"
    assert asset["path"].startswith("media/")


def test_capture_one_missing_image_raises_typed(tmp_path):
    (tmp_path / "media").mkdir()
    with pytest.raises(cap.CaptureError) as e:
        cap.capture_one({"name": "X", "beats": [4], "image": "/nope.png"},
                        tmp_path / "media", tmp_path)
    assert e.value.code == cap.ERR_BAD_IMAGE


def test_capture_one_records_provided_logo(tmp_path):
    img = tmp_path / "site.png"; img.write_bytes(PNG_SIG + b"site")
    logo = tmp_path / "logo.png"; logo.write_bytes(PNG_SIG + b"logo")
    (tmp_path / "media").mkdir()
    asset = cap.capture_one(
        {"name": "Granola", "beats": [4], "image": str(img), "logo": str(logo)},
        tmp_path / "media", tmp_path)
    assert asset["logo"] == "media/logo_granola.png"
    assert (tmp_path / asset["logo"]).read_bytes().startswith(PNG_SIG)


def test_capture_one_logo_none_when_absent(tmp_path):
    img = tmp_path / "site.png"; img.write_bytes(PNG_SIG + b"site")
    (tmp_path / "media").mkdir()
    asset = cap.capture_one(
        {"name": "Otter", "beats": [4], "image": str(img)}, tmp_path / "media", tmp_path)
    assert asset["logo"] is None


def test_capture_one_no_source_raises_typed(tmp_path):
    (tmp_path / "media").mkdir()
    with pytest.raises(cap.CaptureError) as e:
        cap.capture_one({"name": "X", "beats": [4]}, tmp_path / "media", tmp_path)
    assert e.value.code == cap.ERR_MISSING_SOURCE


def test_capture_one_non_png_payload_rejected(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"<html>not a png</html>")
    (tmp_path / "media").mkdir()
    with pytest.raises(cap.CaptureError) as e:
        cap.capture_one({"name": "X", "beats": [4], "image": str(bad)},
                        tmp_path / "media", tmp_path)
    assert e.value.code == cap.ERR_BAD_IMAGE


# ------------------------------------------------------------- orchestration

def _script(d):
    (d / "script.json").write_text(json.dumps({
        "slug": "proj", "title": "t", "hook": "h", "outro": "o", "cta": "c",
        "products": [{"name": "Granola", "beats": [4]}],
        "beats": [{"id": 4, "narration": "Granola rocks", "b_roll_keywords": ["x"]}],
    }))


def test_init_writes_unconfirmed_scaffold(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pipeline import manifest
    d = manifest.project_dir("proj")
    _script(d)
    r = cap._init("proj")
    assert r["success"] is True
    pj = json.loads((d / "products.json").read_text())
    assert pj[0]["name"] == "Granola" and pj[0]["confirmed"] is False


def test_capture_refuses_when_nothing_confirmed_and_stays_pending(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pipeline import manifest
    d = manifest.project_dir("proj")
    _script(d)
    cap._init("proj")  # writes confirmed:false
    r = cap._capture("proj")
    assert r["success"] is False
    assert r["error_code"] == cap.ERR_UNCONFIRMED
    assert manifest.stage_done("proj", "capture") is False  # never marked done


def test_capture_partial_confirm_captures_some_warns_rest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pipeline import manifest
    d = manifest.project_dir("proj")
    _script(d)
    img = d / "granola.png"
    img.write_bytes(PNG_SIG + b"x")
    (d / "products.json").write_text(json.dumps([
        {"name": "Granola", "beats": [4], "image": str(img), "confirmed": True},
        {"name": "Otter", "beats": [5], "url": "https://otter.ai/", "confirmed": False},
    ]))
    r = cap._capture("proj")
    assert r["success"] is True
    assert r["captured"] == 1 and r["skipped_unconfirmed"] == 1
    assert manifest.stage_done("proj", "capture") is True
    m = manifest.load("proj")
    asset = m["stages"]["capture"]["assets"][0]
    assert asset["framing"] == "pip" and asset["beats"] == [4]
    assert m["stages"]["capture"]["warnings"][0]["code"] == cap.ERR_UNCONFIRMED
