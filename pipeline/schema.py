"""script.json validation.

Returns a list of human-readable error strings; an empty list means valid.

Beyond the required top-level fields and per-beat narration/keywords, every beat
must carry a UNIQUE POSITIVE INTEGER ``id`` (fix #6): downstream code keys beat
timings and per-beat assets on it, so a missing/duplicate/non-int id silently
corrupts the render.
"""
REQUIRED_TOP = ("slug", "title", "hook", "beats", "outro", "cta")


def _is_positive_int(value):
    # bool is a subclass of int in Python; reject True/False as ids.
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def validate_script(data):
    errs = []
    if not isinstance(data, dict):
        return ["script.json must be an object"]
    for key in REQUIRED_TOP:
        if key not in data or data[key] in (None, ""):
            errs.append(f"missing required field: {key}")
    beats = data.get("beats")
    if not isinstance(beats, list) or not beats:
        errs.append("beats must be a non-empty array")
        return errs

    seen_ids = set()
    for i, beat in enumerate(beats):
        if not beat.get("narration"):
            errs.append(f"beat[{i}] missing narration")
        kws = beat.get("b_roll_keywords")
        if not isinstance(kws, list) or not kws:
            errs.append(f"beat[{i}] b_roll_keywords must be a non-empty array")

        bid = beat.get("id")
        if bid is None:
            errs.append(f"beat[{i}] missing required field: id")
        elif not _is_positive_int(bid):
            errs.append(
                f"beat[{i}] id must be a positive integer (got {bid!r})")
        elif bid in seen_ids:
            errs.append(f"beat[{i}] id must be unique (duplicate id {bid})")
        else:
            seen_ids.add(bid)
    return errs


def validate_products(products, valid_beat_ids):
    """Validate an optional ``products`` array (yt-capture input).

    ``products`` is None/absent -> valid (the feature is opt-in). When present it
    must be a list of ``{name, beats:[ids]}`` objects where each name is a
    non-empty string and each beat id is a positive int that EXISTS as a real
    body beat in the script (never a card id 0/-1). Returns error strings; empty
    means valid. (autoplan eng F7: validators previously ignored this silently.)
    """
    if products is None:
        return []
    errs = []
    if not isinstance(products, list):
        return ["products must be an array"]
    valid = set(valid_beat_ids)
    for i, p in enumerate(products):
        if not isinstance(p, dict):
            errs.append(f"products[{i}] must be an object")
            continue
        if not p.get("name") or not isinstance(p.get("name"), str):
            errs.append(f"products[{i}] missing non-empty string name")
        beats = p.get("beats")
        if not isinstance(beats, list) or not beats:
            errs.append(f"products[{i}] beats must be a non-empty array")
            continue
        for b in beats:
            if not _is_positive_int(b):
                errs.append(
                    f"products[{i}] beat {b!r} must be a positive integer")
            elif b not in valid:
                errs.append(
                    f"products[{i}] beat {b} is not a body beat in this script")
    return errs
