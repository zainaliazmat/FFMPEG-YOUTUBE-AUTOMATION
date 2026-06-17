from pipeline import env


def test_loads_keys_into_environ(tmp_path, monkeypatch):
    monkeypatch.delenv("FOO_KEY", raising=False)
    p = tmp_path / ".env"
    p.write_text("FOO_KEY=abc123\n")
    env.load_dotenv(p)
    import os
    assert os.environ["FOO_KEY"] == "abc123"


def test_does_not_overwrite_existing(tmp_path, monkeypatch):
    monkeypatch.setenv("FOO_KEY", "already")
    p = tmp_path / ".env"
    p.write_text("FOO_KEY=fromfile\n")
    env.load_dotenv(p)
    import os
    assert os.environ["FOO_KEY"] == "already"


def test_ignores_comments_blanks_and_quotes(tmp_path, monkeypatch):
    for k in ("A_KEY", "B_KEY"):
        monkeypatch.delenv(k, raising=False)
    p = tmp_path / ".env"
    p.write_text('# comment\n\nA_KEY="quoted"\n  B_KEY = spaced \nexport C_KEY=cval\n')
    env.load_dotenv(p)
    import os
    assert os.environ["A_KEY"] == "quoted"
    assert os.environ["B_KEY"] == "spaced"
    assert os.environ["C_KEY"] == "cval"


def test_missing_file_is_noop(tmp_path):
    # Must not raise when there is no .env.
    env.load_dotenv(tmp_path / "nope.env")
