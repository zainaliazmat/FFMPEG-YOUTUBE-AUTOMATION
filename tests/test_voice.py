import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "generate_voice",
    pathlib.Path(".claude/skills/yt-voice/scripts/generate_voice.py"))
gv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gv)


def test_plan_beats_orders_hook_first():
    script = {"hook": "H", "outro": "O", "cta": "C",
              "beats": [{"id": 1, "narration": "A", "b_roll_keywords": ["k"]},
                        {"id": 2, "narration": "B", "b_roll_keywords": ["k"]}]}
    plan = gv.plan_beats(script)
    assert [p["text"] for p in plan] == ["H", "A", "B", "O"]


def test_plan_beats_skips_empty():
    script = {"hook": "H", "outro": "", "cta": "C",
              "beats": [{"id": 1, "narration": "A", "b_roll_keywords": ["k"]}]}
    assert [p["text"] for p in gv.plan_beats(script)] == ["H", "A"]


def test_plan_beats_tags_hook_and_outro_ids():
    # stitch needs to know which timeline entries are hook (0) / outro (-1)
    # so it can render title cards for them.
    script = {"hook": "H", "outro": "O", "cta": "C",
              "beats": [{"id": 5, "narration": "A", "b_roll_keywords": ["k"]}]}
    plan = gv.plan_beats(script)
    assert [p["id"] for p in plan] == [0, 5, -1]


def test_concat_timings_cumulative():
    t = gv.concat_timings([1.0, 2.0, 0.5])
    assert t == [
        {"id": 0, "start": 0.0, "end": 1.0},
        {"id": 1, "start": 1.0, "end": 3.0},
        {"id": 2, "start": 3.0, "end": 3.5},
    ]


def test_concat_timings_carry_plan_ids():
    # When given the plan, timings must carry the real beat ids (0, beat ids, -1),
    # not positional indices — stitch maps assets to beats by id.
    plan = [{"id": 0, "text": "H"}, {"id": 7, "text": "A"}, {"id": -1, "text": "O"}]
    t = gv.concat_timings([1.0, 2.0, 0.5], ids=[p["id"] for p in plan])
    assert [x["id"] for x in t] == [0, 7, -1]
    assert t[1] == {"id": 7, "start": 1.0, "end": 3.0}


# === Fix #4: ONE consistent channel voice with a MATCHING lang_code ===
# The plan's rotation allowlist mixed American (af_/am_) and British (bf_) voices
# while lang_code was hardcoded to 'a' — a real mismatch. Phase 1 locks a single
# voice whose accent prefix matches LANG_CODE, with a clean seam for later rotation.

def test_single_locked_voice_is_deterministic():
    assert gv.pick_voice("slug-one") == gv.pick_voice("slug-two") == gv.VOICE


def test_voice_accent_matches_lang_code():
    # Kokoro convention: voice name's first letter is the accent
    # ('a'=American, 'b'=British) and MUST equal lang_code.
    assert gv.VOICE[0] == gv.LANG, (
        f"voice {gv.VOICE!r} accent does not match lang_code {gv.LANG!r}")


def test_pick_voice_override_seam():
    # The rotation seam exists but is inert in Phase 1 unless explicitly overridden.
    assert gv.pick_voice("any", override="am_michael") == "am_michael"
