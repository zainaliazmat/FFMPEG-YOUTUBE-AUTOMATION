"""Per-beat asset reconciliation: merge captured product stills with stock b-roll.

The two upstream stages speak different shapes:

* ``yt-media`` writes one asset per beat, keyed by a SINGULAR ``beat`` id:
  ``{"beat": 4, "path": ..., "source": "pexels", ...}``.
* ``yt-capture`` maps ONE product capture to MANY beats (a tool mentioned in
  beats 4,5,6 can reuse the same shot), so its records carry a PLURAL
  ``beats: [4,5,6]`` list and a ``framing: "pip"`` tag.

``yt-stitch`` consumes a single ``{beat: asset}`` map. This module is the
reconciliation step the trimmed design needs (autoplan eng F1): it fans the
plural capture records out to singular per-beat records and overlays them on
the stock map, with the captured product still WINNING for any beat it covers.
A beat with no product capture keeps its stock b-roll, so stitch never sees a
gap (the never-blank-beat floor — see ``yt-stitch.plan_segments``).
"""


def fan_out_capture(capture_assets):
    """Expand each ``{beats:[ids], ...}`` capture record into one singular
    ``{beat:id, ...}`` record per beat. ``beats`` is dropped; everything else
    (path, source, license, framing) is copied onto each per-beat record."""
    out = []
    for a in capture_assets or []:
        beats = a.get("beats", [])
        rest = {k: v for k, v in a.items() if k != "beats"}
        for bid in beats:
            out.append({**rest, "beat": bid})
    return out


def merge_assets(media_assets, capture_assets):
    """Return a ``{beat_id: asset}`` map. Stock b-roll is the floor; a captured
    product still overrides it for any beat the capture covers (capture wins).
    Later capture records win over earlier ones for the same beat (stable)."""
    by_beat = {a["beat"]: a for a in (media_assets or [])}
    for a in fan_out_capture(capture_assets):
        by_beat[a["beat"]] = a
    return by_beat
