from pipeline import assets


def test_fan_out_expands_plural_beats_to_singular():
    cap = [{"beats": [4, 5, 6], "path": "media/granola.png",
            "source": "capture", "framing": "pip"}]
    out = assets.fan_out_capture(cap)
    assert [r["beat"] for r in out] == [4, 5, 6]
    # plural key dropped; everything else copied onto each record
    assert all("beats" not in r for r in out)
    assert all(r["path"] == "media/granola.png" and r["framing"] == "pip"
               for r in out)


def test_fan_out_handles_empty_and_none():
    assert assets.fan_out_capture([]) == []
    assert assets.fan_out_capture(None) == []
    assert assets.fan_out_capture([{"beats": [], "path": "x"}]) == []


def test_merge_capture_wins_over_stock_per_beat():
    media = [{"beat": 4, "path": "media/beat_4.mp4", "source": "pexels"},
             {"beat": 7, "path": "media/beat_7.mp4", "source": "pexels"}]
    cap = [{"beats": [4], "path": "media/granola.png",
            "source": "capture", "framing": "pip"}]
    by_beat = assets.merge_assets(media, cap)
    assert by_beat[4]["source"] == "capture"      # product wins for beat 4
    assert by_beat[4]["framing"] == "pip"
    assert by_beat[7]["source"] == "pexels"        # untouched stock beat


def test_merge_keeps_stock_floor_when_no_capture():
    media = [{"beat": 1, "path": "media/beat_1.mp4", "source": "pixabay"}]
    by_beat = assets.merge_assets(media, [])
    assert by_beat == {1: media[0]}


def test_merge_one_capture_covers_many_beats():
    media = [{"beat": b, "path": f"media/beat_{b}.mp4"} for b in (4, 5, 6)]
    cap = [{"beats": [4, 5, 6], "path": "media/tool.png", "framing": "pip"}]
    by_beat = assets.merge_assets(media, cap)
    assert all(by_beat[b]["path"] == "media/tool.png" for b in (4, 5, 6))
