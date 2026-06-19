import json

from pipeline import schema


def test_valid_fixture():
    data = json.load(open("fixtures/script.json"))
    assert schema.validate_script(data) == []


def test_missing_hook():
    errs = schema.validate_script({"slug": "x", "beats": []})
    assert any("hook" in e for e in errs)


def test_beat_requires_keywords():
    bad = {"slug": "x", "title": "t", "hook": "h", "outro": "o", "cta": "c",
           "beats": [{"id": 1, "narration": "n", "b_roll_keywords": []}]}
    errs = schema.validate_script(bad)
    assert any("b_roll_keywords" in e for e in errs)


# --- Fix #6: every beat must have a UNIQUE POSITIVE INTEGER id ---
# Downstream (timings, asset-by-beat lookup) indexes on beat id. The plan's
# schema never validates id, so these all pass on the broken version.

def _script(beats):
    return {"slug": "x", "title": "t", "hook": "h", "outro": "o", "cta": "c",
            "beats": beats}


def test_beat_missing_id_is_error():
    errs = schema.validate_script(_script(
        [{"narration": "n", "b_roll_keywords": ["k"]}]))
    assert any("id" in e for e in errs)


def test_beat_duplicate_id_is_error():
    errs = schema.validate_script(_script([
        {"id": 1, "narration": "a", "b_roll_keywords": ["k"]},
        {"id": 1, "narration": "b", "b_roll_keywords": ["k"]},
    ]))
    assert any("id" in e and ("uniq" in e.lower() or "duplicate" in e.lower())
               for e in errs)


def test_beat_non_integer_id_is_error():
    errs = schema.validate_script(_script(
        [{"id": "1", "narration": "n", "b_roll_keywords": ["k"]}]))
    assert any("id" in e for e in errs)


def test_beat_bool_id_is_error():
    # bool is an int subclass in Python; must be rejected as a beat id.
    errs = schema.validate_script(_script(
        [{"id": True, "narration": "n", "b_roll_keywords": ["k"]}]))
    assert any("id" in e for e in errs)


def test_beat_non_positive_id_is_error():
    for bad_id in (0, -3):
        errs = schema.validate_script(_script(
            [{"id": bad_id, "narration": "n", "b_roll_keywords": ["k"]}]))
        assert any("id" in e for e in errs), bad_id


def test_valid_unique_positive_ids_pass():
    errs = schema.validate_script(_script([
        {"id": 1, "narration": "a", "b_roll_keywords": ["k"]},
        {"id": 2, "narration": "b", "b_roll_keywords": ["k"]},
    ]))
    assert errs == []


def test_validate_motion_absent_is_valid():
    assert schema.validate_motion(None, {-1, 0, 8}) == []


def test_validate_motion_good_card_items():
    m = [
        {"beat": -1, "kind": "card", "template": "card/outro", "confirmed": False},
        {"beat": 8, "kind": "card", "template": "card/chapter", "confirmed": True},
    ]
    assert schema.validate_motion(m, {-1, 0, 8}) == []


def test_validate_motion_rejects_nonbool_confirmed():
    m = [{"beat": 8, "kind": "card", "template": "card/chapter", "confirmed": "true"}]
    errs = schema.validate_motion(m, {8})
    assert any("confirmed must be a boolean" in e for e in errs)


def test_validate_motion_rejects_bad_kind_beat_and_template():
    m = [{"beat": 99, "kind": "explode", "template": "", "confirmed": False}]
    errs = schema.validate_motion(m, {8})
    assert any("kind" in e for e in errs)
    assert any("beat 99" in e for e in errs)
    assert any("template" in e for e in errs)
