"""Canonical output spec shared by the motion renderer and yt-stitch. Both must
agree on size/fps/pixel-format/color or concatenated motion segments judder or
shift color against FFmpeg footage."""
WIDTH = 1920
HEIGHT = 1080
FPS = 30
PIXFMT = "yuv420p"
COLOR = "bt709"   # matrix/primaries/transfer for the motion encode
RANGE = "tv"      # limited range, matches typical FFmpeg footage


def size_str():
    return f"{WIDTH}x{HEIGHT}"
