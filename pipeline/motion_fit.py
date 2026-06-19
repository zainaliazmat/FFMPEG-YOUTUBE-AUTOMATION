"""Timing-fit for motion cards.

Outro card fills the outro segment via an elastic HOLD (never stretching the
intro/outro animation), capped so a mis-tagged runaway outro warns instead of
freezing for 40s. Chapter card is a fixed short flash that must leave footage
behind it on the chapter's first beat."""


def outro_hold(comp_min_s, outro_s, max_card_s):
    """Return (hold_seconds, warn). hold = outro_s - comp_min_s, NEVER clamped:
    the outro card IS the outro, so it always fills the full window (rendered
    length == outro segment length -> no freeze/desync). warn flags a long outro
    so the operator can sanity-check, but the card still fills it."""
    return round(max(outro_s - comp_min_s, 0.0), 3), outro_s > max_card_s


def chapter_fits(beat_s, card_s, min_footage_s):
    """A chapter flash fits only if the beat can host the flash and still show
    footage afterward."""
    return beat_s >= card_s + min_footage_s
