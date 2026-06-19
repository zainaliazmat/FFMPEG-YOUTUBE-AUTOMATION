from pipeline import motion_fit


def test_outro_hold_fills_full_window_within_threshold():
    # comp min 2.0, outro 7.0 -> hold 5.0 (fills the whole 7s), no warn
    assert motion_fit.outro_hold(2.0, 7.0, 8.0) == (5.0, False)


def test_outro_hold_long_outro_warns_but_does_not_clamp():
    # outro 40s -> hold 38.0 (still fills the full window), warn=True
    assert motion_fit.outro_hold(2.0, 40.0, 8.0) == (38.0, True)


def test_chapter_fits_only_with_room_for_flash_plus_footage():
    assert motion_fit.chapter_fits(11.0, 3.0, 2.0) is True    # 11 >= 3 + 2
    assert motion_fit.chapter_fits(4.0, 3.0, 2.0) is False    # 4 < 3 + 2
