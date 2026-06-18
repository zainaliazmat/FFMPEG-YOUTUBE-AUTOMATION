"""yt-discover: find proven, high-demand topics via YouTube Data API v3.

Strategy: enumerate seed channels CHEAPLY and score each video against the
channel's own median views (an "outlier" = a video that beat its channel's
baseline). High outliers across multiple seed channels = repeatable demand.

Quota (free, 10,000 units/day): channels.list (1) -> uploads playlist (UC->UU,
fallback to channels.list) -> playlistItems.list (1) -> videos.list by 50 ids (1).
We AVOID search.list (100 units, no view counts). ~2-3 units per 50-video scan.

The pure functions below are fully TDD'd. The IO wrapper (`discover`) is exercised
live with a YOUTUBE_API_KEY (gated, like the Phase-1 smoke tests).
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pipeline import env, result  # noqa: E402

API = "https://www.googleapis.com/youtube/v3"
_ISO = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


# ----------------------------------------------------------------- pure helpers

def parse_iso8601_duration(s):
    """ISO-8601 duration ('PT1H2M3S') -> total seconds. Bad/empty input -> 0."""
    m = _ISO.fullmatch(s or "")
    if not m:
        return 0
    h, mi, se = (int(x) if x else 0 for x in m.groups())
    return h * 3600 + mi * 60 + se


def is_short(seconds, threshold=180):
    """True if a video is a Short (<= 3 min by default). Boundary is inclusive."""
    return seconds <= threshold


def uploads_playlist_id(channel_id):
    """UC... channel id -> UU... uploads playlist id. Caller falls back to
    channels.list?part=contentDetails if this 404s (UC->UU is a convention)."""
    return "UU" + channel_id[2:] if channel_id.startswith("UC") else channel_id


def median(values):
    v = sorted(values)
    n = len(v)
    if n == 0:
        return 0.0
    mid = n // 2
    return float(v[mid]) if n % 2 else (v[mid - 1] + v[mid]) / 2


def outlier_score(views, baseline_median):
    """views / channel baseline. Guards div-by-zero -> 0.0."""
    return round(views / baseline_median, 2) if baseline_median > 0 else 0.0


def views_per_hour(views, published_iso, now=None):
    now = now or datetime.now(timezone.utc)
    pub = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
    hours = max((now - pub).total_seconds() / 3600, 1.0)
    return round(views / hours, 1)


def _too_recent(published_iso, cutoff_h, now=None):
    now = now or datetime.now(timezone.utc)
    pub = datetime.fromisoformat(published_iso.replace("Z", "+00:00"))
    return (now - pub).total_seconds() / 3600 < cutoff_h


def rank_videos(videos, min_views_floor=10000, recent_cutoff_h=72, now=None):
    """videos: [{id,title,views,duration_s,published}]. Returns outlier-ranked
    long-form videos: Shorts filtered, sub-floor suppressed, baseline = median of
    the channel's non-Short, non-recent uploads (recent videos haven't had time
    to accumulate views, so they'd deflate the baseline)."""
    longform = [v for v in videos if not is_short(v["duration_s"])]
    baseline_pool = [v["views"] for v in longform
                     if not _too_recent(v["published"], recent_cutoff_h, now)]
    base = median(baseline_pool) if baseline_pool else median(
        [v["views"] for v in longform])
    scored = []
    for v in longform:
        if v["views"] < min_views_floor:
            continue
        scored.append({**v,
                       "outlier": outlier_score(v["views"], base),
                       "vph": views_per_hour(v["views"], v["published"], now)})
    return sorted(scored, key=lambda x: x["outlier"], reverse=True)


COMMERCIAL_TERMS = ("best", "review", "vs", "top ", "how to", "tutorial",
                    "guide", "alternative", "pricing", "worth it")


def commercial_intent_flag(title):
    """Keyword heuristic: does the title signal advertiser-friendly commercial intent?"""
    t = (title or "").lower()
    return any(term in t for term in COMMERCIAL_TERMS)


# ----------------------------------------------------------------- IO wrapper

def _get(path, params, api_key, _tries=4):
    params = {**params, "key": api_key}
    url = f"{API}/{path}?{urllib.parse.urlencode(params)}"
    for attempt in range(_tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            if e.code in (403, 429, 500, 503) and attempt < _tries - 1:
                time.sleep(2 ** attempt)  # backoff on rate-limit / transient
                continue
            raise


def _uploads_id(channel_id, api_key):
    # cheap UC->UU convention first; verify/fallback via channels.list
    data = _get("channels", {"part": "contentDetails", "id": channel_id}, api_key)
    items = data.get("items", [])
    if items:
        return items[0]["contentDetails"]["relatedPlaylists"]["uploads"]
    return uploads_playlist_id(channel_id)


def _video_ids(uploads_id, api_key, max_videos=50):
    ids, page = [], None
    while len(ids) < max_videos:
        params = {"part": "contentDetails", "playlistId": uploads_id,
                  "maxResults": 50}
        if page:
            params["pageToken"] = page
        data = _get("playlistItems", params, api_key)
        ids += [it["contentDetails"]["videoId"] for it in data.get("items", [])]
        page = data.get("nextPageToken")
        if not page:
            break
    return ids[:max_videos]


def _videos(video_ids, api_key):
    out = []
    for i in range(0, len(video_ids), 50):
        batch = video_ids[i:i + 50]
        data = _get("videos",
                    {"part": "statistics,contentDetails,snippet",
                     "id": ",".join(batch)}, api_key)
        for it in data.get("items", []):
            stats = it.get("statistics", {})
            if "viewCount" not in stats:  # hidden stats -> skip
                continue
            sn = it.get("snippet", {})
            out.append({
                "id": it["id"],
                "title": sn.get("title", ""),
                "channel": sn.get("channelTitle", ""),
                "views": int(stats["viewCount"]),
                "duration_s": parse_iso8601_duration(
                    it.get("contentDetails", {}).get("duration", "")),
                "published": sn.get("publishedAt", "1970-01-01T00:00:00Z"),
            })
    return out


def discover(channel_path="channel.json", top_n=25, root="project"):
    env.load_dotenv()
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        return result.err("YOUTUBE_API_KEY not set (.env)")
    channel = json.loads(Path(channel_path).read_text())
    seeds = channel.get("seed_channels", [])
    if not seeds:
        return result.err("no seed_channels in channel.json")

    pool = []
    for cid in seeds:
        try:
            uploads = _uploads_id(cid, api_key)
            vids = _videos(_video_ids(uploads, api_key), api_key)
            pool += rank_videos(vids)  # rank per-channel (per-channel baseline)
        except Exception as exc:  # noqa: BLE001 - one bad channel shouldn't kill the run
            print(f"warn: {cid} failed: {exc}", file=sys.stderr)

    ranked = sorted(pool, key=lambda x: x["outlier"], reverse=True)[:top_n]
    topics = [{
        "title": v["title"], "channel": v["channel"],
        "url": f"https://youtube.com/watch?v={v['id']}",
        "views": v["views"], "outlier": v["outlier"], "vph": v["vph"],
        "commercial_intent": commercial_intent_flag(v["title"]),
    } for v in ranked]

    out_dir = Path(root) / "_discovery"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "topics.json").write_text(json.dumps(topics, indent=2))
    return result.ok(artifact="_discovery/topics.json", count=len(topics),
                     top=[t["title"] for t in topics[:5]])


if __name__ == "__main__":
    result.run(discover)
