from pathlib import Path
import json

from pipeline import result


def test_ok_shape():
    r = result.ok(path="a.wav")
    assert r == {"success": True, "error": None, "path": "a.wav"}


def test_err_shape():
    r = result.err("boom", stage="voice")
    assert r == {"success": False, "error": "boom", "stage": "voice"}


def test_run_catches_exception():
    def bad():
        raise ValueError("nope")
    r = result.run(bad)
    assert r["success"] is False
    assert "nope" in r["error"]


def test_run_passes_through():
    r = result.run(lambda: result.ok(n=1))
    assert r == {"success": True, "error": None, "n": 1}


# --- Fix #6: robust envelope written to project/<slug>/.result.json ---
# Stages print to stdout alongside kokoro/whisperx/ffmpeg noise, so the
# envelope must be retrievable from a known file, not "the last stdout line".

def test_run_writes_result_file_on_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    r = result.run(lambda: result.ok(n=1), slug="demo")
    rp = tmp_path / "project" / "demo" / ".result.json"
    assert rp.exists(), "run(slug=...) must persist the envelope to .result.json"
    assert json.loads(rp.read_text()) == r == {"success": True, "error": None, "n": 1}


def test_run_writes_result_file_on_exception(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    def bad():
        raise ValueError("kaboom")

    r = result.run(bad, slug="demo")
    rp = tmp_path / "project" / "demo" / ".result.json"
    assert rp.exists()
    persisted = json.loads(rp.read_text())
    assert persisted["success"] is False
    assert "kaboom" in persisted["error"]


def test_run_no_slug_writes_no_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    result.run(lambda: result.ok(n=1))
    assert not (tmp_path / "project").exists()
