"""yt-media — Pexels/Pixabay b-roll fetch + cache + backoff + license log.

Fix #1: the saved file extension is derived from the API's DECLARED media type
(Pexels `video_files[].file_type`, Pixabay videos are mp4, or the download
Content-Type) — NEVER from the URL string. Pexels video links are Vimeo-external
URLs with a query string and no ".mp4"/"video" token, so the plan's
`url.endswith(("mp4","/")) or "video" in url` would save an mp4 as .jpg and the
render would die looping it as a still.

Fix #5: there is NO public Pixabay music API, so this stage does NOT call any
music endpoint. Background music (optional) comes from a local CC0 file dropped
into a `music/` folder (YouTube Audio Library / Pixabay-downloaded).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path

from pipeline import result, manifest, env

PEXELS_LICENSE = "Pexels License (free commercial, no attribution)"
PIXABAY_LICENSE = "Pixabay Content License (free commercial)"
CACHE_DIR = Path(".cache/media")
MAX_BYTES = 200_000_000  # don't OOM/fill disk on a UHD clip
AUDIO_EXTS = (".mp3", ".m4a", ".aac", ".wav", ".ogg", ".flac")

_MIME_EXT = {
    "video/mp4": ".mp4", "video/quicktime": ".mov", "video/webm": ".webm",
    "image/jpeg": ".jpg", "image/jpg": ".jpg", "image/png": ".png",
    "image/webp": ".webp",
}


def pick_pexels_video(resp, max_w=1920):
    vids = resp.get("videos") or []
    if not vids:
        return None
    files = sorted(vids[0].get("video_files", []), key=lambda f: f.get("width", 0))
    if not files:
        return None
    eligible = [f for f in files if f.get("width", 0) <= max_w] or files
    chosen = eligible[-1]
    return {"url": chosen["link"], "license": PEXELS_LICENSE,
            "file_type": chosen.get("file_type")}


def pick_pexels_photo(resp):
    photos = resp.get("photos") or []
    if not photos:
        return None
    return {"url": photos[0]["src"]["large2x"], "license": PEXELS_LICENSE,
            "file_type": "image/jpeg"}


def pick_pixabay(resp, kind):
    hits = resp.get("hits") or []
    if not hits:
        return None
    h = hits[0]
    if kind == "photo":
        url = h.get("largeImageURL")
        return {"url": url, "license": PIXABAY_LICENSE,
                "file_type": "image/jpeg"} if url else None
    if kind == "video":
        url = h["videos"]["large"]["url"]  # Pixabay videos are always mp4
        return {"url": url, "license": PIXABAY_LICENSE,
                "file_type": "video/mp4"} if url else None
    # Fix #5: no public Pixabay music API — refuse the kind outright.
    raise ValueError(
        f"unsupported media kind {kind!r}: there is no public Pixabay music API")


def extension_for(pick, content_type=None):
    """Extension from DECLARED media type, with the download Content-Type as a
    fallback. NEVER inferred from the URL string."""
    mime = (pick.get("file_type") if isinstance(pick, dict) else None) or content_type or ""
    mime = mime.split(";")[0].strip().lower()
    if mime in _MIME_EXT:
        return _MIME_EXT[mime]
    if mime.startswith("video/"):
        return ".mp4"
    if mime.startswith("image/"):
        return ".jpg"
    raise ValueError(f"cannot determine extension from media type {mime!r}")


def find_local_music(music_dir):
    """Optional background music: first audio file in the music/ folder, or None."""
    p = Path(music_dir)
    if not p.is_dir():
        return None
    for f in sorted(p.iterdir()):
        if f.is_file() and f.suffix.lower() in AUDIO_EXTS:
            return f
    return None


def backoff_delays(n, base=1.0, cap=30.0):
    return [min(base * (2 ** i), cap) for i in range(n)]


def cache_key(url):
    return hashlib.sha1(url.encode()).hexdigest()


def _get_json(url, headers=None, params=None, retries=5):
    import time
    import requests
    for delay in [0.0] + backoff_delays(retries):
        if delay:
            time.sleep(delay)
        r = requests.get(url, headers=headers or {}, params=params or {}, timeout=30)
        if r.status_code == 429:
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError(f"rate-limited after {retries} retries: {url}")


def _download(url, dest, max_bytes=MAX_BYTES):
    """Stream to a content-addressed cache, then copy to dest. Returns the
    download's Content-Type (for extension fallback)."""
    import requests
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / cache_key(url)
    ctype_path = cached.with_suffix(".ctype")
    if not cached.exists():
        with requests.get(url, timeout=120, stream=True) as r:
            r.raise_for_status()
            ctype = r.headers.get("Content-Type", "")
            total = 0
            with open(cached, "wb") as f:
                for chunk in r.iter_content(chunk_size=1 << 16):
                    total += len(chunk)
                    if total > max_bytes:
                        cached.unlink(missing_ok=True)
                        raise RuntimeError(
                            f"asset exceeds {max_bytes} bytes: {url}")
                    f.write(chunk)
        ctype_path.write_text(ctype)
    dest.write_bytes(cached.read_bytes())
    return ctype_path.read_text() if ctype_path.exists() else ""


def _fetch(slug, force=False):
    env.load_dotenv()  # pick up keys from a gitignored .env (does not overwrite real env)
    pexels_key = os.environ.get("PEXELS_API_KEY")
    pixabay_key = os.environ.get("PIXABAY_API_KEY")
    if not pexels_key and not pixabay_key:
        return result.err("set PEXELS_API_KEY and/or PIXABAY_API_KEY")
    if manifest.stage_done(slug, "media") and not force:
        return result.ok(skipped=True, stage="media")

    d = manifest.project_dir(slug)
    script = json.loads((d / "script.json").read_text())
    assets = []
    for beat in script["beats"]:
        kw = " ".join(beat["b_roll_keywords"])
        pick = source = None
        if pexels_key:
            resp = _get_json("https://api.pexels.com/videos/search",
                             headers={"Authorization": pexels_key},
                             params={"query": kw, "per_page": 1})
            pick = pick_pexels_video(resp)
            source = "pexels"
        if not pick and pixabay_key:
            resp = _get_json("https://pixabay.com/api/videos/",
                             params={"key": pixabay_key, "q": kw, "per_page": 3})
            pick = pick_pixabay(resp, "video")
            source = "pixabay"
        if not pick:
            return result.err(f"no media for beat {beat['id']} ({kw})")

        # Derive extension from the DECLARED type; fall back to Content-Type after
        # the download if the API didn't declare one.
        try:
            ext = extension_for(pick)
            dest = d / "media" / f"beat_{beat['id']}{ext}"
            ctype = _download(pick["url"], dest)
        except ValueError:
            tmp = d / "media" / f"beat_{beat['id']}.tmp"
            ctype = _download(pick["url"], tmp)
            ext = extension_for(pick, content_type=ctype)
            dest = d / "media" / f"beat_{beat['id']}{ext}"
            tmp.rename(dest)

        assets.append({"beat": beat["id"], "path": str(dest.relative_to(d)),
                       "source": source, "license": pick["license"],
                       "file_type": pick.get("file_type") or ctype})

    music = find_local_music("music")
    music_rel = None
    if music:
        music_dest = d / "audio" / ("music" + music.suffix.lower())
        music_dest.write_bytes(music.read_bytes())
        music_rel = str(music_dest.relative_to(d))

    manifest.set_stage(slug, "media", status="done", assets=assets,
                       music=music_rel, music_license=(
                           "local CC0 (YouTube Audio Library / Pixabay)"
                           if music_rel else None))
    return result.ok(assets=len(assets), music=music_rel)


def main():
    ap = argparse.ArgumentParser(description="Fetch b-roll for a project slug")
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    result.run(lambda: _fetch(args.slug, args.force), slug=args.slug)


if __name__ == "__main__":
    main()
