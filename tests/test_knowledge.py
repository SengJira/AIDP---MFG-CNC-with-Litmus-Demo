import json
from glob import glob
from pathlib import Path

import pandas as pd

KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
INDEX_PATH = Path(__file__).parent.parent / "data" / "processed" / "knowledge_index.json"


def test_knowledge_files_present():
    paths = sorted(glob(str(KNOWLEDGE_DIR / "*.md")))
    assert len(paths) >= 6
    titles = [Path(p).stem for p in paths]
    assert "spindle_bearing_wear" in titles
    assert "cnc01_maintenance_log" in titles


def test_knowledge_index_json():
    if not INDEX_PATH.exists():
        # index can be created on demand by scripts/index_knowledge.py
        return
    docs = json.loads(INDEX_PATH.read_text())
    assert len(docs) >= 6
    df = pd.DataFrame(docs)
    assert "title" in df.columns
    assert "content" in df.columns
    assert "tfidf" in df.columns
