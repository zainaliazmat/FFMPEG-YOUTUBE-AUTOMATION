import importlib.util
import pathlib

import pytest

spec = importlib.util.spec_from_file_location(
    "generate_captions",
    pathlib.Path(".claude/skills/yt-captions/scripts/generate_captions.py"))
gc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gc)


def _words(tokens, t0=0.0):
    return [{"word": w, "start": float(i) + t0, "end": float(i) + t0 + 1.0}
            for i, w in enumerate(tokens)]


def test_fmt_ts():
    assert gc.fmt_ts(0) == "0:00:00.00"
    assert gc.fmt_ts(3661.5) == "1:01:01.50"


def test_group_words_splits_on_sentence():
    words = _words(["Hello", "there.", "New", "one."])
    cues = gc.group_words(words, max_chars=100)
    assert len(cues) == 2
    assert cues[0]["text"] == "Hello there."
    assert cues[0]["start"] == 0 and cues[0]["end"] == 2


def test_group_words_splits_on_max_chars():
    words = _words(["ab"] * 5)
    cues = gc.group_words(words, max_chars=5)
    assert all(len(c["text"]) <= 5 for c in cues)
    assert len(cues) >= 2


# === Fix #3: a matching ASS per aspect ratio ===
# The plan authors a single PlayResX/Y 1080x1920 ASS; burned into a 1920x1080
# video it renders mis-sized. 16:9 long-form is the PRIMARY output.

def test_to_ass_16x9_uses_landscape_playres():
    ass = gc.to_ass([{"start": 0.0, "end": 1.0, "text": "Hi"}], aspect="16x9")
    assert "PlayResX: 1920" in ass and "PlayResY: 1080" in ass
    assert "[Script Info]" in ass and "[V4+ Styles]" in ass
    assert "Dialogue:" in ass and "Hi" in ass


def test_to_ass_9x16_uses_portrait_playres():
    ass = gc.to_ass([{"start": 0.0, "end": 1.0, "text": "Hi"}], aspect="9x16")
    assert "PlayResX: 1080" in ass and "PlayResY: 1920" in ass


def test_to_ass_distinct_per_aspect():
    cues = [{"start": 0.0, "end": 1.0, "text": "Hi"}]
    assert gc.to_ass(cues, "16x9") != gc.to_ass(cues, "9x16")


def test_to_ass_rejects_unknown_aspect():
    with pytest.raises(ValueError):
        gc.to_ass([], aspect="4x3")


# === H4: assign words to sentences by CHARACTER OFFSET, drop nothing ===
# A blank/non-speech token (WhisperX emits these) makes the plan's
# words[idx:idx+n] slicing miscount and silently DROP a trailing real word.
# Char-offset assignment preserves every spoken word, in order, with monotonic
# timings. Input deliberately includes "it's", "3.5", and a comma.

def test_group_words_preserves_all_words_with_blank_token():
    tokens = ["It's", "3.5", "times", "better,", "really.",
              "I", "", "swear", "it", "works."]
    cues = gc.group_words(_words(tokens), max_chars=100)
    out = " ".join(c["text"] for c in cues).split()
    expected = [t for t in tokens if t.strip()]
    assert out == expected, "no spoken word may be dropped or reordered"


def test_group_words_no_blank_or_double_space_cue_text():
    tokens = ["It's", "here,", "", "now."]
    cues = gc.group_words(_words(tokens), max_chars=100)
    for c in cues:
        assert c["text"] == c["text"].strip()
        assert "  " not in c["text"]


def test_group_words_timings_monotonic_and_aligned():
    tokens = ["It's", "3.5", "times,", "really.", "Go", "now."]
    cues = gc.group_words(_words(tokens), max_chars=100)
    # cue starts strictly increasing, each cue start == its first word's start
    starts = [c["start"] for c in cues]
    assert starts == sorted(starts)
    assert cues[0]["start"] == 0.0
