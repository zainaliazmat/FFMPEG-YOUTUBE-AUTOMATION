"""yt-captions — WhisperX word timings + PySBD sentences -> styled ASS.

Fix #3: a separate ASS is authored per aspect ratio (PlayRes 1080x1920 for 9:16,
1920x1080 for 16:9), with a proportionally sized font. A single 1080x1920 ASS
burned into a 1920x1080 video renders mis-sized; 16:9 long-form is the primary
output, so it must get a matching caption file.

H4: words are assigned to PySBD sentences by CHARACTER OFFSET (not by re-splitting
the sentence on whitespace and slicing the word list by count). Word-count slicing
silently desyncs on contractions / numbers / punctuation, cascading the error
through every later cue.
"""
import argparse

from pipeline import result, manifest

# PlayRes + font size per aspect. Font size is tuned to each canvas height.
ASPECTS = {
    "9x16": {"w": 1080, "h": 1920, "fontsize": 90, "marginv": 200},
    "16x9": {"w": 1920, "h": 1080, "fontsize": 64, "marginv": 90},
}


def fmt_ts(seconds):
    cs = int(round(seconds * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _sentence_spans(full, sentences):
    """Char [start,end) of each sentence within `full`, scanning left to right so
    PySBD's whitespace handling can't shift the mapping."""
    spans, cur = [], 0
    for s in sentences:
        s = s.strip()
        if not s:
            continue
        idx = full.find(s, cur)
        if idx < 0:
            idx = cur
        spans.append((idx, idx + len(s)))
        cur = idx + len(s)
    return spans


def group_words(words, max_chars=42):
    """Word dicts {word,start,end} -> cues {start,end,text}. Splits at PySBD
    sentence boundaries and at max_chars, assigning words to sentences by the
    word's character offset in the joined text."""
    import pysbd

    # Drop blank / non-speech tokens (WhisperX emits these); the plan's
    # word-count slicing would otherwise miscount and drop trailing real words.
    words = [w for w in words if (w.get("word") or "").strip()]
    if not words:
        return []

    # Build the joined text and record each word's char span in it.
    full = ""
    word_starts = []
    for i, w in enumerate(words):
        tok = w["word"].strip()
        if i > 0:
            full += " "
        word_starts.append(len(full))
        full += tok

    seg = pysbd.Segmenter(language="en", clean=False)
    spans = _sentence_spans(full, seg.segment(full)) or [(0, len(full))]

    def sentence_index(char_pos):
        for si, (a, b) in enumerate(spans):
            if a <= char_pos < b:
                return si
        return len(spans) - 1

    # Group words by sentence (char-offset), then wrap at max_chars within each.
    cues = []
    cur_sentence = None
    cur, cur_start = [], None
    for w, ws in zip(words, word_starts):
        si = sentence_index(ws)
        tok = w["word"].strip()
        tentative = " ".join([*[c["word"].strip() for c in cur], tok])
        starts_new = (si != cur_sentence) or (cur and len(tentative) > max_chars)
        if starts_new and cur:
            cues.append({"start": cur_start, "end": cur[-1]["end"],
                         "text": " ".join(c["word"].strip() for c in cur)})
            cur, cur_start = [], None
        if not cur:
            cur_start = w["start"]
        cur.append(w)
        cur_sentence = si
    if cur:
        cues.append({"start": cur_start, "end": cur[-1]["end"],
                     "text": " ".join(c["word"].strip() for c in cur)})
    return cues


def _header(aspect):
    a = ASPECTS[aspect]
    return (
        "[Script Info]\n"
        "ScriptType: v4.00+\n"
        f"PlayResX: {a['w']}\n"
        f"PlayResY: {a['h']}\n\n"
        "[V4+ Styles]\n"
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, "
        "BackColour, Bold, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding\n"
        f"Style: Default,DejaVu Sans,{a['fontsize']},&H00FFFFFF,&H00000000,"
        f"&H00000000,1,1,4,2,2,60,60,{a['marginv']},1\n\n"
        "[Events]\n"
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, "
        "Effect, Text\n"
    )


def to_ass(cues, aspect="16x9"):
    """Full ASS document sized for the given aspect."""
    if aspect not in ASPECTS:
        raise ValueError(f"unknown aspect {aspect!r}")
    lines = [_header(aspect)]
    for c in cues:
        text = c["text"].replace("\n", " ")
        lines.append(
            f"Dialogue: 0,{fmt_ts(c['start'])},{fmt_ts(c['end'])},Default,,0,0,0,,{text}")
    return "\n".join(lines) + "\n"


def ass_filename(aspect):
    return f"captions_{aspect}.ass"


def _transcribe(slug, force=False):
    import whisperx

    if manifest.stage_done(slug, "captions") and not force:
        return result.ok(skipped=True, stage="captions")
    d = manifest.project_dir(slug)
    wav = d / "audio" / "voiceover.wav"
    model = whisperx.load_model("base", device="cpu", compute_type="int8")
    audio = whisperx.load_audio(str(wav))
    tx = model.transcribe(audio, batch_size=4)
    align_model, meta = whisperx.load_align_model(language_code="en", device="cpu")
    aligned = whisperx.align(tx["segments"], align_model, meta, audio, "cpu")
    words = [{"word": w["word"], "start": w.get("start", 0.0), "end": w.get("end", 0.0)}
             for seg in aligned["segments"] for w in seg.get("words", [])
             if w.get("start") is not None]
    cues = group_words(words)

    artifacts = {}
    for aspect in ASPECTS:
        fn = ass_filename(aspect)
        (d / fn).write_text(to_ass(cues, aspect))
        artifacts[aspect] = fn
    manifest.set_stage(slug, "captions", status="done", artifacts=artifacts,
                       cues=len(cues))
    return result.ok(cues=len(cues), artifacts=artifacts)


def main():
    ap = argparse.ArgumentParser(description="Generate captions for a project slug")
    ap.add_argument("slug")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    result.run(lambda: _transcribe(args.slug, args.force), slug=args.slug)


if __name__ == "__main__":
    main()
