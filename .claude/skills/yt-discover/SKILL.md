---
name: yt-discover
description: Find proven, high-demand, advertiser-friendly video topics via the free YouTube Data API v3, using median-based outlier scoring against seed channels. Produces a ranked project/_discovery/topics.json for human topic selection (Gate 1). Use to decide WHAT to make next.
---

# yt-discover

Finds topics with **proven demand** by scanning a set of seed channels in your
niche and scoring each video against its own channel's median views. A video that
beat its channel's baseline is an "outlier" — evidence the *topic/angle* works.
The agent extracts the **pattern** (topic + angle); it never copies a video.

## Run
`python .claude/skills/yt-discover/scripts/discover.py`

- reads `seed_channels` (a `["UC...", ...]` array) and `min`/`top` config from `channel.json`
- needs `YOUTUBE_API_KEY` in `.env`
- writes ranked `project/_discovery/topics.json` (outlier, views, vph, commercial-intent, title, channel, url)
- prints the standard `{"success": ...}` envelope + the top 5 titles

## Setup (human)
1. Google Cloud project -> enable **YouTube Data API v3** -> create an **API key**
   (public read needs only the key, no OAuth). Put it in `.env` as `YOUTUBE_API_KEY`.
2. Add seed channel ids to `channel.json` as `"seed_channels": ["UC...", ...]`
   (3-8 strong channels in the niche works well).

## Quota (free: 10,000 units/day)
Enumerate cheaply — **avoid `search.list` (100 units, and it returns no view counts).**
- `channels.list?part=contentDetails` (1 unit) -> uploads playlist id
  (UC... -> UU... convention, with a `channels.list` fallback the code already does)
- `playlistItems.list?part=contentDetails&maxResults=50` (1 unit) -> video ids
- `videos.list?part=statistics,contentDetails,snippet&id=<up to 50>` (1 unit)

~2-3 units per 50-video channel scan. A dozen channels/day costs well under quota.

## Scoring
- **Baseline** = median views of the channel's non-Short, non-recent uploads
  (recent videos haven't accrued views yet; flops legitimately lower the median).
- **outlier_score** = views / baseline. Shorts (<=180s) are dropped; sub-10k-view
  videos are suppressed from the ranking.
- **views_per_hour** captures momentum on newer videos.
- **commercial_intent_flag** = keyword heuristic ("best", "review", "vs", "how to",
  "pricing", "worth it"...) for advertiser-friendly intent.

### Thresholds (heuristics, not gospel)
- **3x+** outlier = strong signal. **10x+** = breakout.
- An outlier appearing across **multiple** seed channels = repeatable demand — the
  strongest signal. Treat the ranked queue as candidates for human judgment.

## Output handoff
`project/_discovery/topics.json` feeds **Gate 1** (human topic review) in the
`yt-pipeline` flow. A picked topic becomes the seed for a `yt-script` draft.

## Stats hygiene (already handled in code)
- `statistics.viewCount` is a string -> cast to int; videos with hidden/absent stats
  are skipped.
- `contentDetails.duration` is ISO-8601 -> parsed to seconds.
- 403/429/500/503 get exponential backoff; one failing channel doesn't kill the run.
