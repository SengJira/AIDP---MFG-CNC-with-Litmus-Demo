#!/usr/bin/env python3
"""Index knowledge markdown into a local JSON search index and, optionally, Elasticsearch.

A sentence-transformer model can be swapped in by setting SENTENCE_TRANSFORMERS_MODEL.
By default we build a TF-IDF vector fallback so the demo needs no extra model download.
"""

import json
import os
import re
from glob import glob
from pathlib import Path

from sklearn.feature_extraction.text import TfidfVectorizer


KNOWLEDGE_DIR = Path(__file__).parent.parent / "knowledge"
OUT_DIR = Path(__file__).parent.parent / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def read_markdown(path: Path):
    text = path.read_text()
    # title is first H1
    title = path.stem.replace("_", " ").title()
    for line in text.splitlines():
        if line.startswith("# "):
            title = line.lstrip("# ").strip()
            break
    return {
        "id": path.stem,
        "title": title,
        "content": text,
        "source": str(path),
    }


def build_local_index(docs):
    vectorizer = TfidfVectorizer(stop_words="english", ngram_range=(1, 2), min_df=1)
    contents = [d["content"] for d in docs]
    tfidf = vectorizer.fit_transform(contents)
    feature_names = vectorizer.get_feature_names_out()
    rows = tfidf.toarray()
    for doc, row in zip(docs, rows):
        nonzero = {feature_names[i]: float(row[i]) for i in row.nonzero()[0]}
        doc["tfidf"] = nonzero
    return docs


def index_to_elastic(docs):
    es_endpoint = os.environ.get("ELASTIC_ENDPOINT")
    es_api_key = os.environ.get("ELASTIC_API_KEY")
    if not es_endpoint or not es_api_key:
        print("[index_knowledge] ELASTIC_ENDPOINT or ELASTIC_API_KEY not set; skipping Elastic upload.")
        return
    try:
        from elasticsearch import Elasticsearch
    except Exception as exc:
        print(f"[index_knowledge] elasticsearch client not available: {exc}")
        return
    es = Elasticsearch(es_endpoint, api_key=es_api_key, verify_certs=False)
    if not es.ping():
        print("[index_knowledge] Elastic ping failed; skipping upload.")
        return
    index_name = "cnc_knowledge"
    if not es.indices.exists(index=index_name):
        es.indices.create(
            index=index_name,
            body={
                "settings": {"number_of_shards": 1, "number_of_replicas": 0},
                "mappings": {
                    "properties": {
                        "title": {"type": "text"},
                        "content": {"type": "text"},
                        "doc_id": {"type": "keyword"},
                    }
                },
            },
            ignore=400,
        )
    for doc in docs:
        es.index(index=index_name, id=doc["id"], body={
            "doc_id": doc["id"],
            "title": doc["title"],
            "content": doc["content"],
        })
    es.indices.refresh(index=index_name)
    print(f"[index_knowledge] Indexed {len(docs)} documents to {index_name} on {es_endpoint}")


def main():
    paths = sorted(glob(str(KNOWLEDGE_DIR / "*.md")))
    if not paths:
        raise SystemExit(f"No markdown files found in {KNOWLEDGE_DIR}")
    docs = [read_markdown(Path(p)) for p in paths]
    docs = build_local_index(docs)
    out_path = OUT_DIR / "knowledge_index.json"
    with open(out_path, "w") as f:
        json.dump(docs, f, indent=2)
    print(f"[index_knowledge] Wrote local index with {len(docs)} docs to {out_path}")
    index_to_elastic(docs)


if __name__ == "__main__":
    main()
