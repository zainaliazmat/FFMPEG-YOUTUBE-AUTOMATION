from pipeline import manifest


def test_init_and_load(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    m = manifest.init("demo")
    assert m["slug"] == "demo"
    assert m["stages"]["voice"]["status"] == "pending"
    assert manifest.load("demo")["slug"] == "demo"


def test_project_dir_creates_subdirs(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    d = manifest.project_dir("demo")
    assert (d / "audio").is_dir()
    assert (d / "media").is_dir()
    assert (d / "out").is_dir()


def test_set_stage_and_done(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    manifest.init("demo")
    manifest.set_stage("demo", "voice", status="done", artifact="audio/voiceover.wav")
    assert manifest.stage_done("demo", "voice") is True
    assert manifest.stage_done("demo", "media") is False
    assert manifest.load("demo")["stages"]["voice"]["artifact"] == "audio/voiceover.wav"


def test_stage_done_false_when_no_manifest(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert manifest.stage_done("missing", "voice") is False


def test_set_stage_auto_inits_when_manifest_absent(tmp_path, monkeypatch):
    # A stage may be the first to touch a project (no orchestrator pre-init).
    # set_stage must create the manifest rather than fail on a missing file.
    monkeypatch.chdir(tmp_path)
    manifest.project_dir("fresh")  # dirs exist, but no manifest.json yet
    manifest.set_stage("fresh", "voice", status="done", artifact="audio/voiceover.wav")
    m = manifest.load("fresh")
    assert m["slug"] == "fresh"
    assert m["stages"]["voice"]["status"] == "done"
    # other known stages still present and pending
    assert m["stages"]["stitch"]["status"] == "pending"
