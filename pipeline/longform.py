"""Long-form (8-20 min) script contract: word/duration math + validator.

The spine's ``schema.validate_script`` enforces the base contract (required top
fields + per-beat narration/keywords/id). This module layers the long-form and
monetization rules on top: real duration in the channel's target range, chapters
for navigation, at least one mid-roll break, a minimum of cited sources, and an
explicit per-video ``channel_pov`` (the "transformative take" that keeps the
channel inside YouTube's July-2025 inauthentic-content policy).

The extended ``script.json`` stays backward-compatible: the spine reads the base
fields and ignores chapters/midroll_beats/sources/channel_pov/word_count/etc.
"""
from pipeline import schema


def word_count(script):
    """Total words across hook + every beat narration + outro."""
    parts = [script.get("hook", ""), script.get("outro", "")]
    parts += [b.get("narration", "") for b in script.get("beats", [])]
    return sum(len((p or "").split()) for p in parts)


def estimate_duration_min(words, wpm=140):
    """Spoken minutes at ``wpm`` words/minute (guards wpm <= 0)."""
    return round(words / max(wpm, 1), 2)


def validate_longform_script(data, channel=None):
    """Return a list of error strings (empty = valid long-form script).

    Reuses the spine's base contract first, then enforces the long-form rules.
    """
    if not isinstance(data, dict):
        return ["script.json must be an object"]

    errs = list(schema.validate_script(data))  # base spine contract

    # Beat ids: schema.validate_script already checks these, but keep an
    # explicit long-form guard so the rule survives even if the base loosens.
    ids = [b.get("id") for b in data.get("beats", [])]
    if any((not isinstance(i, int) or isinstance(i, bool) or i <= 0)
           for i in ids):
        errs.append("every beat id must be a positive integer")
    if len(set(ids)) != len(ids):
        errs.append("beat ids must be unique")

    ch = channel or {}
    lo, hi = ch.get("target_length_min", [8, 20])
    dur = data.get("estimated_duration_min")
    if not isinstance(dur, (int, float)) or isinstance(dur, bool) \
            or not (lo <= dur <= hi):
        errs.append(
            f"estimated_duration_min {dur} outside long-form range {lo}-{hi}")

    if len(data.get("chapters", [])) < 4:
        errs.append("need >=4 chapters")
    if len(data.get("midroll_beats", [])) < 1:
        errs.append("need >=1 midroll beat for an 8min+ video")

    min_sources = ch.get("min_sources", 5)
    if len(data.get("sources", [])) < min_sources:
        errs.append(f"need >={min_sources} cited sources")

    if not data.get("channel_pov"):
        errs.append("channel_pov required")

    # Optional products[] (yt-capture input). Absent = valid; when present, each
    # entry's beats must be real body beats so a typo can't silently mis-target
    # capture (autoplan eng F7). Validated against the body-beat ids.
    errs += schema.validate_products(
        data.get("products"), [b.get("id") for b in data.get("beats", [])])

    return errs
