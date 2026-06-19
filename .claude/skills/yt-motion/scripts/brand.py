"""Inject the COMMITTED brand system into a project. Deterministic: copies the
hand-authored templates verbatim. It never derives design from channel.json."""
import sys
import shutil
from pathlib import Path

# Make `pipeline` importable when run as a script (mirrors capture_sites.py:38).
sys.path.insert(0, str(Path(__file__).resolve().parents[4]))

from pipeline import manifest  # noqa: E402

_TEMPLATES = Path(__file__).resolve().parent.parent / "templates"


def generate(slug, root="project"):
    d = manifest.project_dir(slug, root) / "motion"
    d.mkdir(parents=True, exist_ok=True)
    tokens, frame = d / "tokens.css", d / "brand.md"
    shutil.copyfile(_TEMPLATES / "tokens.css", tokens)
    shutil.copyfile(_TEMPLATES / "brand.md", frame)
    return {"tokens": str(tokens), "frame": str(frame)}
