"""Long-form schema + math tests.

Each validation test must DISCRIMINATE: it flips exactly one field on a known-good
fixture and asserts the matching error appears, so a no-op validator fails.
"""
import copy
import json

import pytest

from pipeline import longform, schema

VALID = json.load(open("fixtures/longform_script.json"))
CHANNEL = json.load(open("channel.json"))


def test_valid_fixture_passes():
    assert longform.validate_longform_script(VALID, CHANNEL) == []


def test_spine_still_accepts_richer_fixture():
    # The extended contract must remain backward-compatible: the EXISTING base
    # validator ignores the extra fields and still returns [].
    assert schema.validate_script(VALID) == []


def test_duration_too_short_flagged():
    bad = copy.deepcopy(VALID)
    bad["estimated_duration_min"] = 3.0
    errs = longform.validate_longform_script(bad, CHANNEL)
    assert any("estimated_duration_min" in e for e in errs)


def test_duration_too_long_flagged():
    bad = copy.deepcopy(VALID)
    bad["estimated_duration_min"] = 45.0
    errs = longform.validate_longform_script(bad, CHANNEL)
    assert any("estimated_duration_min" in e for e in errs)


def test_two_chapters_flagged():
    bad = copy.deepcopy(VALID)
    bad["chapters"] = VALID["chapters"][:2]
    errs = longform.validate_longform_script(bad, CHANNEL)
    assert any("chapter" in e for e in errs)


def test_empty_midroll_flagged():
    bad = copy.deepcopy(VALID)
    bad["midroll_beats"] = []
    errs = longform.validate_longform_script(bad, CHANNEL)
    assert any("midroll" in e for e in errs)


def test_too_few_sources_flagged():
    bad = copy.deepcopy(VALID)
    bad["sources"] = VALID["sources"][:4]
    errs = longform.validate_longform_script(bad, CHANNEL)
    assert any("source" in e for e in errs)


def test_empty_channel_pov_flagged():
    bad = copy.deepcopy(VALID)
    bad["channel_pov"] = ""
    errs = longform.validate_longform_script(bad, CHANNEL)
    assert any("channel_pov" in e for e in errs)


def test_duplicate_beat_id_flagged():
    bad = copy.deepcopy(VALID)
    bad["beats"][1]["id"] = bad["beats"][0]["id"]  # force [1, 1, ...]
    errs = longform.validate_longform_script(bad, CHANNEL)
    assert any("id" in e and ("uniq" in e.lower() or "unique" in e.lower())
               for e in errs)


def test_non_positive_beat_id_flagged():
    bad = copy.deepcopy(VALID)
    bad["beats"][0]["id"] = 0
    errs = longform.validate_longform_script(bad, CHANNEL)
    assert any("positive integer" in e for e in errs)


# --- pure math ---

def test_word_count_known_script():
    script = {"hook": "one two three", "outro": "four five",
              "beats": [{"narration": "six seven"}, {"narration": "eight"}]}
    # 3 + 2 + 2 + 1 = 8
    assert longform.word_count(script) == 8


def test_estimate_duration_min():
    assert longform.estimate_duration_min(1400, 140) == 10.0


def test_estimate_duration_guards_zero_wpm():
    # must not raise ZeroDivisionError
    assert longform.estimate_duration_min(1400, 0) == 1400.0
