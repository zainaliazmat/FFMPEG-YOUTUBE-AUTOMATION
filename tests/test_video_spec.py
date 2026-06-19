from pipeline import video_spec as vs


def test_canonical_spec_values():
    assert (vs.WIDTH, vs.HEIGHT, vs.FPS) == (1920, 1080, 30)
    assert vs.PIXFMT == "yuv420p"
    assert vs.COLOR == "bt709" and vs.RANGE == "tv"
    assert vs.size_str() == "1920x1080"
