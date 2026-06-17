import importlib.util
import pathlib

spec = importlib.util.spec_from_file_location(
    "fetch_media",
    pathlib.Path(".claude/skills/yt-media/scripts/fetch_media.py"))
fm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fm)


def test_pick_pexels_video_picks_largest_within_cap():
    resp = {"videos": [{"video_files": [
        {"width": 640, "height": 360, "file_type": "video/mp4", "link": "lo.mp4"},
        {"width": 1920, "height": 1080, "file_type": "video/mp4", "link": "hi.mp4"},
        {"width": 3840, "height": 2160, "file_type": "video/mp4", "link": "uhd.mp4"},
    ]}]}
    pick = fm.pick_pexels_video(resp)
    assert pick["url"] == "hi.mp4"
    assert "pexels" in pick["license"].lower()


def test_pick_pexels_video_none_when_empty():
    assert fm.pick_pexels_video({"videos": []}) is None


def test_pick_pixabay_photo():
    resp = {"hits": [{"largeImageURL": "p.jpg"}]}
    pick = fm.pick_pixabay(resp, "photo")
    assert pick["url"] == "p.jpg"
    assert "pixabay" in pick["license"].lower()


def test_backoff_is_exponential_and_capped():
    assert fm.backoff_delays(5, base=1.0, cap=8.0) == [1.0, 2.0, 4.0, 8.0, 8.0]


def test_cache_key_stable():
    assert fm.cache_key("http://x/y") == fm.cache_key("http://x/y")
    assert fm.cache_key("a") != fm.cache_key("b")


# === Fix #1: extension from DECLARED media type, not URL string ===
# Pexels video links look like a Vimeo external URL with a query string and no
# ".mp4" suffix and no "video" token. The plan's
#   url.endswith(("mp4","/")) or "video" in url  -> ".jpg"
# would save an mp4 as .jpg and the render dies looping it as a still.

VIMEO_LINK = ("https://player.vimeo.com/external/"
              "123456789.hd.mp4?s=deadbeef&profile_id=175&oauth2_token_id=abc")


def test_pexels_video_pick_carries_declared_type():
    resp = {"videos": [{"video_files": [
        {"width": 1920, "height": 1080, "file_type": "video/mp4", "link": VIMEO_LINK},
    ]}]}
    pick = fm.pick_pexels_video(resp)
    assert pick["url"] == VIMEO_LINK
    assert pick["file_type"] == "video/mp4"


def test_extension_for_query_string_video_is_mp4():
    # The exact trap: a video URL with a query string and no "mp4"/"video" token.
    pick = {"url": VIMEO_LINK, "file_type": "video/mp4"}
    assert fm.extension_for(pick) == ".mp4"


def test_extension_for_photo_is_jpg():
    pick = {"url": "https://images.pexels.com/photos/1/x.jpeg?auto=compress",
            "file_type": "image/jpeg"}
    assert fm.extension_for(pick) == ".jpg"


def test_extension_for_falls_back_to_content_type_header():
    # When the API gave no declared type, derive from the download Content-Type,
    # NOT from the URL string.
    pick = {"url": VIMEO_LINK, "file_type": None}
    assert fm.extension_for(pick, content_type="video/mp4") == ".mp4"


def test_pixabay_video_carries_declared_type():
    resp = {"hits": [{"videos": {"large": {"url": VIMEO_LINK}}}]}
    pick = fm.pick_pixabay(resp, "video")
    assert pick["url"] == VIMEO_LINK
    assert pick["file_type"] == "video/mp4"
    assert fm.extension_for(pick) == ".mp4"


# === Fix #5: NO Pixabay music endpoint; optional LOCAL CC0 music only ===

def test_pick_pixabay_has_no_music_kind():
    # Phase 1 must not call any Pixabay music endpoint (there is no public one).
    import pytest
    with pytest.raises((ValueError, KeyError)):
        fm.pick_pixabay({"hits": [{}]}, "music")


def test_find_local_music_returns_none_when_absent(tmp_path):
    assert fm.find_local_music(tmp_path / "music") is None


def test_find_local_music_returns_file_when_present(tmp_path):
    mdir = tmp_path / "music"
    mdir.mkdir()
    track = mdir / "calm.mp3"
    track.write_bytes(b"ID3")
    assert fm.find_local_music(mdir) == track
