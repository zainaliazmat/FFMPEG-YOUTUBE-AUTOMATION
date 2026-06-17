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


# === Resilience: a Pexels ERROR must fall back to Pixabay, not kill the run ===
# The plan's _fetch lets a Pexels exception (e.g. a 401 on a specific query)
# propagate, so the whole render dies even though Pixabay (the documented
# fallback) would have served the beat.

def test_pexels_error_falls_back_to_pixabay(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PEXELS_API_KEY", "pexkey")
    monkeypatch.setenv("PIXABAY_API_KEY", "pixkey")
    proj = tmp_path / "project" / "demo"
    (proj / "media").mkdir(parents=True)
    (proj).joinpath("script.json").write_text(
        '{"slug":"demo","title":"t","hook":"h","outro":"o","cta":"c",'
        '"beats":[{"id":1,"narration":"n","b_roll_keywords":["laptop"]}]}')

    def fake_get_json(url, headers=None, params=None, retries=5):
        if "pexels" in url:
            raise RuntimeError("401 Client Error: Unauthorized (Invalid API key)")
        return {"hits": [{"videos": {"large": {"url": "http://pix/v.mp4"}}}]}

    def fake_download(url, dest, max_bytes=fm.MAX_BYTES):
        dest.write_bytes(b"\x00\x00\x00")
        return "video/mp4"

    monkeypatch.setattr(fm, "_get_json", fake_get_json)
    monkeypatch.setattr(fm, "_download", fake_download)

    r = fm._fetch("demo")
    assert r["success"] is True, r
    from pipeline import manifest
    assets = manifest.load("demo")["stages"]["media"]["assets"]
    assert len(assets) == 1
    assert assets[0]["source"] == "pixabay"  # fell back, did not crash
    assert assets[0]["path"].endswith(".mp4")
