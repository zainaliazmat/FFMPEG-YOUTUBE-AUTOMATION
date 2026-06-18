"""yt-discover pure-function tests. Each must DISCRIMINATE, not just smoke-run."""
import importlib.util
import pathlib
from datetime import datetime, timedelta, timezone

SCRIPT = pathlib.Path(".claude/skills/yt-discover/scripts/discover.py")
spec = importlib.util.spec_from_file_location("discover", SCRIPT)
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def test_parse_iso8601_duration():
    assert dc.parse_iso8601_duration("PT1H2M3S") == 3723
    assert dc.parse_iso8601_duration("PT30S") == 30
    assert dc.parse_iso8601_duration("PT5M") == 300
    assert dc.parse_iso8601_duration("PT1H") == 3600
    assert dc.parse_iso8601_duration("") == 0
    assert dc.parse_iso8601_duration(None) == 0


def test_is_short_boundary():
    assert dc.is_short(45) is True
    assert dc.is_short(180) is True       # boundary inclusive
    assert dc.is_short(200) is False


def test_uploads_playlist_id():
    assert dc.uploads_playlist_id("UCabc") == "UUabc"
    # non-UC id passes through unchanged
    assert dc.uploads_playlist_id("PLxyz") == "PLxyz"


def test_median():
    assert dc.median([1, 2, 3]) == 2
    assert dc.median([1, 2, 3, 4]) == 2.5
    assert dc.median([]) == 0.0


def test_outlier_score():
    assert dc.outlier_score(1000, 200) == 5.0
    assert dc.outlier_score(5, 0) == 0.0   # div-by-zero guard


def test_views_per_hour():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    two_h_ago = (now - timedelta(hours=2)).isoformat().replace("+00:00", "Z")
    assert dc.views_per_hour(7200, two_h_ago, now=now) == 3600.0


def test_commercial_intent_flag():
    assert dc.commercial_intent_flag("Best AI tools for writing") is True
    assert dc.commercial_intent_flag("ChatGPT vs Claude") is True
    assert dc.commercial_intent_flag("a quiet vlog") is False


def test_rank_videos_filters_and_sorts():
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    old = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    videos = [
        {"id": "a", "title": "long winner", "views": 100000, "duration_s": 600, "published": old},
        {"id": "b", "title": "long mid", "views": 50000, "duration_s": 600, "published": old},
        {"id": "c", "title": "a short", "views": 999999, "duration_s": 30, "published": old},   # Short -> excluded
        {"id": "d", "title": "sub floor", "views": 500, "duration_s": 600, "published": old},    # < floor -> excluded
    ]
    ranked = dc.rank_videos(videos, min_views_floor=10000, now=now)
    ids = [v["id"] for v in ranked]
    assert ids == ["a", "b"]               # Short + sub-floor excluded from ranking
    assert ranked[0]["outlier"] >= ranked[1]["outlier"]   # sorted desc
    # baseline includes the sub-floor long-form flop (it's a real non-Short,
    # non-recent upload): median([100000, 50000, 500]) = 50000 -> a == 2.0
    assert ranked[0]["outlier"] == dc.outlier_score(100000, 50000)


def test_rank_videos_excludes_recent_from_baseline():
    # A brand-new viral video shouldn't deflate the baseline used to score others.
    now = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    old = (now - timedelta(days=30)).isoformat().replace("+00:00", "Z")
    fresh = (now - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    videos = [
        {"id": "established", "title": "x", "views": 80000, "duration_s": 600, "published": old},
        {"id": "fresh-hit", "title": "y", "views": 20000, "duration_s": 600, "published": fresh},
    ]
    ranked = dc.rank_videos(videos, min_views_floor=10000, recent_cutoff_h=72, now=now)
    est = next(v for v in ranked if v["id"] == "established")
    # baseline must be median of the non-recent pool only = 80000, so outlier == 1.0
    assert est["outlier"] == 1.0
