import hashlib
import importlib.util
import pathlib
import re
import shutil
import subprocess

import pytest

spec = importlib.util.spec_from_file_location(
    "stitch_video",
    pathlib.Path(".claude/skills/yt-stitch/scripts/stitch_video.py"))
sv = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sv)

HAVE_FFMPEG = shutil.which("ffmpeg") and shutil.which("ffprobe")
needs_ffmpeg = pytest.mark.skipif(not HAVE_FFMPEG, reason="ffmpeg/ffprobe required")


# ----------------------------------------------------------------- pure builders

def test_scale_pad_9x16():
    f = sv.scale_pad_filter("9x16")
    assert "1080" in f and "1920" in f


def test_scale_pad_16x9():
    f = sv.scale_pad_filter("16x9")
    assert "1920" in f and "1080" in f


def test_zoompan_uses_duration_and_target_dims_not_720():
    clause = sv.zoompan_clause(2.0, "16x9", fps=30)
    assert "zoompan" in clause and "d=60" in clause       # 2.0s * 30fps
    assert "s=1920x1080" in clause                          # C2: target dims
    assert "1280x720" not in clause                         # NOT the plan's 720p


def test_zoompan_target_dims_9x16():
    assert "s=1080x1920" in sv.zoompan_clause(1.0, "9x16", fps=30)


def test_build_command_includes_outputs_and_format():
    segs = [{"id": 1, "kind": "image", "duration": 2.0, "path": "media/beat_1.jpg"}]
    cmd = sv.build_command(segs, None, "captions_16x9.ass",
                           "out/video_16x9.mp4", "16x9")
    assert cmd[0] == "ffmpeg"
    assert "out/video_16x9.mp4" in cmd
    assert "yuv420p" in cmd
    assert "+faststart" in cmd
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "ass='captions_16x9.ass'" in fc


def test_build_command_covers_full_timeline_with_cards():
    # C1: hook card + beat + outro card -> concat must cover ALL THREE segments.
    segs = [
        {"id": 0, "kind": "card", "duration": 1.0, "textfile": "cards/seg_0_16x9.txt"},
        {"id": 1, "kind": "video", "duration": 2.0, "path": "media/beat_1.mp4"},
        {"id": -1, "kind": "card", "duration": 1.0, "textfile": "cards/seg_-1_16x9.txt"},
    ]
    cmd = sv.build_command(segs, None, "captions_16x9.ass", "out/v.mp4", "16x9")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "concat=n=3:v=1:a=0" in fc
    assert "[v0][v1][v2]concat" in fc
    # the hook/outro cards must be rendered as drawtext from their text files
    assert fc.count("drawtext=") == 2


def test_build_command_voice_mapped_directly_without_music():
    segs = [{"id": 1, "kind": "video", "duration": 2.0, "path": "media/b.mp4"}]
    cmd = sv.build_command(segs, None, "c.ass", "out/v.mp4", "16x9")
    # one segment -> voice is input index 1, mapped directly, no amix/sidechain
    assert "-map" in cmd
    maps = [cmd[i + 1] for i, a in enumerate(cmd) if a == "-map"]
    assert "1:a" in maps
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "amix" not in fc and "sidechaincompress" not in fc


def test_build_command_mixes_voice_and_ducked_music():
    segs = [{"id": 1, "kind": "video", "duration": 2.0, "path": "media/b.mp4"}]
    cmd = sv.build_command(segs, "audio/music.mp3", "c.ass", "out/v.mp4", "16x9")
    fc = cmd[cmd.index("-filter_complex") + 1]
    # H1: voice is asplit (one copy keys the compressor, one is amixed back in)
    assert "asplit=2[vkey][vmix]" in fc
    assert "sidechaincompress" in fc
    assert "amix=inputs=2" in fc
    assert "normalize=0" in fc  # voice kept at full level, not halved by amix
    assert "[vmix]" in fc  # the voice copy is mixed back -> never dropped


# ----------------------------------------------------- product PiP + asset floor

def test_pip_inner_dims_are_even_and_reduced():
    iw, ih = sv.pip_inner_dims("16x9")
    assert iw % 2 == 0 and ih % 2 == 0
    assert iw < 1920 and ih < 1080          # reduced size (Bill Graham lever)
    assert iw == 1382 and ih == 778         # 1920*0.72, 1080*0.72 -> even


def test_product_segment_is_pip_on_branded_card_not_full_bleed():
    segs = [{"id": 1, "kind": "product", "duration": 2.0, "path": "media/granola.png"}]
    cmd = sv.build_command(segs, None, "c.ass", "out/v.mp4", "16x9")
    fc = cmd[cmd.index("-filter_complex") + 1]
    # composited onto the branded card (pad with CARD_BG), i.e. NOT full-bleed
    assert f"pad=1920:1080:(ow-iw)/2:(oh-ih)/2:color={sv.CARD_BG}" in fc
    # zoomed/scaled to the reduced PiP inset, not the full frame
    assert "s=1382x778" in fc


def test_plan_segments_routes_product_framing_and_floors_missing_beats(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest = __import__("pipeline.manifest", fromlist=["manifest"])
    manifest.project_dir("proj")
    script = {"hook": "h", "outro": "o"}
    timings = [
        {"id": 0, "start": 0.0, "end": 1.0},
        {"id": 4, "start": 1.0, "end": 3.0},
        {"id": 5, "start": 3.0, "end": 5.0},
        {"id": -1, "start": 5.0, "end": 6.0},
    ]
    by_beat = {
        4: {"beat": 4, "path": "media/granola.png", "framing": "pip"},  # product
        5: {"beat": 5, "path": "media/beat_5.mp4"},                     # stock video
    }
    segs = sv.plan_segments("proj", "16x9", script, timings, by_beat)
    kinds = {s["id"]: s["kind"] for s in segs}
    assert kinds[0] == "card" and kinds[-1] == "card"
    assert kinds[4] == "product"   # framing:pip -> PiP card
    assert kinds[5] == "video"

    # a body beat with no asset must fail with the full missing list, not deep in ffmpeg
    with pytest.raises(RuntimeError) as e:
        sv.plan_segments("proj", "16x9", script, timings, {4: by_beat[4]})
    assert "5" in str(e.value)


def test_logo_segment_fades_in_and_zooms():
    segs = [{"id": 4, "kind": "logo", "duration": 1.8, "path": "media/logo_card.png"}]
    cmd = sv.build_command(segs, None, "c.ass", "out/v.mp4", "16x9")
    fc = cmd[cmd.index("-filter_complex") + 1]
    assert "fade=t=in:st=0:d=0.6" in fc      # reveal
    assert "zoompan=z='min(zoom+0.0012,1.10)'" in fc  # gentle grow
    assert "media/logo_card.png" in cmd


@needs_ffmpeg
def test_plan_segments_splits_first_product_mention_with_logo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest = __import__("pipeline.manifest", fromlist=["manifest"])
    d = manifest.project_dir("proj")
    # a real transparent logo so _logo_card's ffmpeg overlay succeeds
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "color=c=red:s=200x80,format=rgba", "-frames:v", "1",
                    str(d / "media" / "logo_granola.png")], check=True, capture_output=True)
    (d / "media" / "product_granola.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    script = {"hook": "h", "outro": "o"}
    timings = [
        {"id": 0, "start": 0.0, "end": 1.0},
        {"id": 4, "start": 1.0, "end": 11.0},   # Granola first mention -> split
        {"id": 6, "start": 11.0, "end": 21.0},  # Granola again -> NO logo
        {"id": -1, "start": 21.0, "end": 22.0},
    ]
    a = {"path": "media/product_granola.png", "framing": "pip",
         "product": "Granola", "logo": "media/logo_granola.png"}
    by_beat = {4: {"beat": 4, **a}, 6: {"beat": 6, **a}}
    segs = sv.plan_segments("proj", "16x9", script, timings, by_beat)
    beat4 = [s for s in segs if s["id"] == 4]
    beat6 = [s for s in segs if s["id"] == 6]
    assert [s["kind"] for s in beat4] == ["logo", "product"]      # split
    assert abs(sum(s["duration"] for s in beat4) - 10.0) < 0.01   # sums to beat dur
    assert [s["kind"] for s in beat6] == ["product"]              # reveal once only


# --------------------------------------------------------------- real renders

def _ffprobe_duration(path):
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return float(out.strip())


def _streams(path):
    return subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
         "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout


def _mean_volume_db(path):
    out = subprocess.run(
        ["ffmpeg", "-i", str(path), "-af", "volumedetect", "-f", "null", "-"],
        capture_output=True, text=True).stderr
    m = re.search(r"mean_volume:\s*(-?\d+\.?\d*) dB", out)
    return float(m.group(1)) if m else None


def _make_wav(path, dur, freq=440, sr=24000):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"sine=frequency={freq}:duration={dur}:sample_rate={sr}",
         str(path)], check=True, capture_output=True)


def _make_video(path, dur, color="red", size="640x360", fps=30):
    subprocess.run(
        ["ffmpeg", "-y", "-f", "lavfi", "-i",
         f"color=c={color}:s={size}:d={dur}:r={fps}", "-pix_fmt", "yuv420p",
         str(path)], check=True, capture_output=True)


def _ass(text, aspect="16x9"):
    w, h = sv.DIMS[aspect]
    return (
        "[Script Info]\nScriptType: v4.00+\n"
        f"PlayResX: {w}\nPlayResY: {h}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
        "BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        "Style: Default,DejaVu Sans,64,&H00FFFFFF,&H00000000,&H00000000,1,1,"
        "4,2,2,60,60,90,1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
        f"Dialogue: 0,0:00:00.00,0:00:05.00,Default,,0,0,0,,{text}\n")


def _project(tmp_path):
    d = tmp_path / "proj"
    for sub in ("audio", "media", "out", "cards"):
        (d / sub).mkdir(parents=True, exist_ok=True)
    return d


@needs_ffmpeg
def test_render_duration_matches_and_has_streams(tmp_path):
    d = _project(tmp_path)
    _make_wav(d / "audio" / "voiceover.wav", 3.0)
    _make_video(d / "media" / "beat_1.mp4", 2.0, "green")
    (d / "cards" / "seg_0.txt").write_text("Hook card")
    (d / "captions_16x9.ass").write_text(_ass("Hello world"))
    segs = [
        {"id": 0, "kind": "card", "duration": 1.0, "textfile": "cards/seg_0.txt"},
        {"id": 1, "kind": "video", "duration": 2.0, "path": "media/beat_1.mp4"},
    ]
    cmd = sv.build_command(segs, None, "captions_16x9.ass",
                           "out/video_16x9.mp4", "16x9")
    sv.run_ffmpeg(cmd, cwd=d)
    out = d / "out" / "video_16x9.mp4"
    assert out.exists()
    # total video duration == audio duration within ~0.1s (C1/H3)
    assert abs(_ffprobe_duration(out) - 3.0) < 0.15
    streams = _streams(out)
    assert "video" in streams and "audio" in streams


@needs_ffmpeg
def test_render_is_1920x1080_yuv420p(tmp_path):
    d = _project(tmp_path)
    _make_wav(d / "audio" / "voiceover.wav", 2.0)
    _make_video(d / "media" / "beat_1.mp4", 2.0, "blue")
    (d / "captions_16x9.ass").write_text(_ass("x"))
    segs = [{"id": 1, "kind": "video", "duration": 2.0, "path": "media/beat_1.mp4"}]
    sv.run_ffmpeg(sv.build_command(segs, None, "captions_16x9.ass",
                                   "out/v.mp4", "16x9"), cwd=d)
    info = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,pix_fmt", "-of", "csv=p=0", str(d / "out" / "v.mp4")],
        capture_output=True, text=True).stdout.strip()
    assert info == "1920,1080,yuv420p"


@needs_ffmpeg
def test_render_image_zoompan_exact_duration_and_dims(tmp_path):
    # C2: a single still + zoompan d= must produce exactly dur*fps frames at the
    # target dimensions (the plan rendered zoompan at 1280x720 then upscaled).
    d = _project(tmp_path)
    _make_wav(d / "audio" / "voiceover.wav", 2.0)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "color=c=orange:s=800x600:d=1", "-frames:v", "1",
                    str(d / "media" / "beat_1.jpg")], check=True, capture_output=True)
    (d / "cap.ass").write_text(_ass("x"))
    segs = [{"id": 1, "kind": "image", "duration": 2.0, "path": "media/beat_1.jpg"}]
    sv.run_ffmpeg(sv.build_command(segs, None, "cap.ass", "out/img.mp4", "16x9"),
                  cwd=d)
    info = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,pix_fmt", "-of", "csv=p=0", str(d / "out" / "img.mp4")],
        capture_output=True, text=True).stdout.strip()
    assert info == "1920,1080,yuv420p"
    assert abs(_ffprobe_duration(d / "out" / "img.mp4") - 2.0) < 0.15


@needs_ffmpeg
def test_render_product_pip_is_valid_and_correct_dims(tmp_path):
    # The product PiP filter graph must be valid ffmpeg and still output a full
    # 1920x1080 frame (the inset sits on the branded card).
    d = _project(tmp_path)
    _make_wav(d / "audio" / "voiceover.wav", 2.0)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "color=c=white:s=1920x1080:d=1", "-frames:v", "1",
                    str(d / "media" / "granola.png")], check=True, capture_output=True)
    (d / "cap.ass").write_text(_ass("x"))
    segs = [{"id": 1, "kind": "product", "duration": 2.0, "path": "media/granola.png"}]
    sv.run_ffmpeg(sv.build_command(segs, None, "cap.ass", "out/pip.mp4", "16x9"),
                  cwd=d)
    info = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height,pix_fmt", "-of", "csv=p=0", str(d / "out" / "pip.mp4")],
        capture_output=True, text=True).stdout.strip()
    assert info == "1920,1080,yuv420p"
    assert abs(_ffprobe_duration(d / "out" / "pip.mp4") - 2.0) < 0.15


@needs_ffmpeg
def test_render_logo_reveal_valid(tmp_path):
    # logo card -> reveal segment renders to a valid full-frame clip
    d = _project(tmp_path)
    _make_wav(d / "audio" / "voiceover.wav", 3.0)
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "color=c=red:s=200x80,format=rgba", "-frames:v", "1",
                    str(d / "media" / "logo.png")], check=True, capture_output=True)
    card = sv._logo_card("media/logo.png", "16x9", d)
    assert card and (d / card).exists()
    _make_video(d / "media" / "beat_1.mp4", 2.0, "blue")
    (d / "cap.ass").write_text(_ass("x"))
    segs = [
        {"id": 1, "kind": "logo", "duration": 1.0, "path": card},
        {"id": 1, "kind": "video", "duration": 2.0, "path": "media/beat_1.mp4"},
    ]
    sv.run_ffmpeg(sv.build_command(segs, None, "cap.ass", "out/logo.mp4", "16x9"), cwd=d)
    info = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(d / "out" / "logo.mp4")],
        capture_output=True, text=True).stdout.strip()
    assert info == "1920,1080"


@needs_ffmpeg
def test_render_audio_non_silent(tmp_path):
    d = _project(tmp_path)
    _make_wav(d / "audio" / "voiceover.wav", 2.0, freq=440)
    _make_video(d / "media" / "beat_1.mp4", 2.0)
    (d / "captions_16x9.ass").write_text(_ass("x"))
    segs = [{"id": 1, "kind": "video", "duration": 2.0, "path": "media/beat_1.mp4"}]
    sv.run_ffmpeg(sv.build_command(segs, None, "captions_16x9.ass",
                                   "out/v.mp4", "16x9"), cwd=d)
    mv = _mean_volume_db(d / "out" / "v.mp4")
    assert mv is not None and mv > -50.0, f"audio looks silent: {mv} dB"


@needs_ffmpeg
def test_captions_are_burned_in(tmp_path):
    # Render twice, differing ONLY by caption text; the frame during the cue must
    # differ -> the ass filter actually loaded (C3) and drew the text.
    d = _project(tmp_path)
    _make_wav(d / "audio" / "voiceover.wav", 2.0)
    _make_video(d / "media" / "beat_1.mp4", 2.0, "black")
    segs = [{"id": 1, "kind": "video", "duration": 2.0, "path": "media/beat_1.mp4"}]

    def render(ass_text, out_name):
        (d / "cap.ass").write_text(_ass(ass_text))
        sv.run_ffmpeg(sv.build_command(segs, None, "cap.ass", f"out/{out_name}",
                                       "16x9"), cwd=d)
        frame = d / f"{out_name}.png"
        subprocess.run(["ffmpeg", "-y", "-ss", "1.0", "-i", str(d / "out" / out_name),
                        "-frames:v", "1", str(frame)], check=True, capture_output=True)
        return hashlib.sha1(frame.read_bytes()).hexdigest()

    with_text = render("BIG CAPTION HERE", "with.mp4")
    empty = render("", "empty.mp4")
    assert with_text != empty, "captions did not change the frame -> not burned in"


def test_plan_segments_outro_swap_and_chapter_insert(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest = __import__("pipeline.manifest", fromlist=["manifest"])
    d = manifest.project_dir("proj")
    script = {"hook": "h", "outro": "o", "title": "t",
              "chapters": [{"title": "Pricing", "start_beat": 8}]}
    timings = [{"id": 0, "start": 0.0, "end": 3.0},
               {"id": 8, "start": 3.0, "end": 14.0},     # 11s chapter beat
               {"id": -1, "start": 14.0, "end": 20.0}]   # 6s outro
    by_beat = {8: {"beat": 8, "path": "media/beat_8.mp4", "source": "pexels"}}
    motion_cards = {
        8: {"beat": 8, "kind": "card", "path": "media/motion_card_8.mp4", "duration": 3.0},
        -1: {"beat": -1, "kind": "card", "path": "media/motion_card_-1.mp4", "duration": 5.5}}
    segs = sv.plan_segments("proj", "16x9", script, timings, by_beat, motion_cards)
    # outro is now the motion MP4, not a drawtext card; duration = mc["duration"]
    outro = [s for s in segs if s["id"] == -1]
    assert outro[0]["kind"] == "video" and outro[0]["path"] == "media/motion_card_-1.mp4"
    assert outro[0]["duration"] == 5.5     # mc["duration"], not re-derived from the window
    # chapter beat 8: a 3s card flash THEN 8s of footage
    b8 = [s for s in segs if s["id"] == 8]
    assert b8[0]["path"] == "media/motion_card_8.mp4" and b8[0]["duration"] == 3.0
    assert b8[1]["path"] == "media/beat_8.mp4" and b8[1]["duration"] == 8.0


@needs_ffmpeg
def test_voice_not_dropped_when_music_present(tmp_path):
    # H1: with music, the voice must still dominate the mixed audio. The plan's
    # broken graph used the voice only as a sidechain key and dropped it.
    d = _project(tmp_path)
    _make_wav(d / "audio" / "voiceover.wav", 2.0, freq=440)
    _make_wav(d / "audio" / "music.mp3", 2.0, freq=200)
    _make_video(d / "media" / "beat_1.mp4", 2.0)
    (d / "cap.ass").write_text(_ass("x"))
    segs = [{"id": 1, "kind": "video", "duration": 2.0, "path": "media/beat_1.mp4"}]

    sv.run_ffmpeg(sv.build_command(segs, None, "cap.ass", "out/voiceonly.mp4",
                                   "16x9"), cwd=d)
    sv.run_ffmpeg(sv.build_command(segs, "audio/music.mp3", "cap.ass",
                                   "out/mixed.mp4", "16x9"), cwd=d)
    voice_only = _mean_volume_db(d / "out" / "voiceonly.mp4")
    mixed = _mean_volume_db(d / "out" / "mixed.mp4")
    # If the voice were dropped (only ducked music left), mixed would be far
    # quieter. Require it to stay within 3 dB of the voice-only level.
    assert mixed >= voice_only - 3.0, (
        f"voice appears dropped: voice_only={voice_only} mixed={mixed}")
