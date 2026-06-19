from pathlib import Path
import brand


def test_generate_copies_committed_tokens_deterministically(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from pipeline import manifest
    manifest.project_dir("demo")
    out1 = brand.generate("demo")
    tokens = Path(out1["tokens"]).read_text()
    frame = Path(out1["frame"]).read_text()
    assert "--ease: cubic-bezier(0.22, 1, 0.36, 1)" in tokens
    assert "motion confirms, it doesn't sell" in frame
    out2 = brand.generate("demo")
    assert Path(out2["tokens"]).read_text() == tokens
    assert Path(out2["frame"]).read_text() == frame
