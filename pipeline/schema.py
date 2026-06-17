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
