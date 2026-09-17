from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np

from .artifacts import ArtifactDefinition
from .config import EMBEDDING_MODEL, EMBEDDING_ROOT, PRINCIPLES_ROOT
from .embeddings import retrieve


CACHE_DIR = EMBEDDING_ROOT / "_artifact_principles"


def _corpus() -> tuple[list[dict[str, Any]], str]:
    chunks: list[dict[str, Any]] = []
    digest = hashlib.sha256()
    for path in sorted(PRINCIPLES_ROOT.glob("*.txt"), key=lambda item: item.name.casefold()):
        text = path.read_text(encoding="utf-8")
        digest.update(path.name.encode("utf-8"))
        digest.update(b"\0")
        digest.update(text.encode("utf-8"))
        digest.update(b"\0")
        paragraphs = [part.strip() for part in text.replace("\r\n", "\n").split("\n\n") if part.strip()]
        current: list[str] = []
        size = 0
        for paragraph in paragraphs:
            if current and size + len(paragraph) > 1600:
                chunks.append({"chunk_id": len(chunks) + 1, "source_filename": path.name, "text": "\n\n".join(current)})
                current, size = [], 0
            current.append(paragraph)
            size += len(paragraph)
        if current:
            chunks.append({"chunk_id": len(chunks) + 1, "source_filename": path.name, "text": "\n\n".join(current)})
    if not chunks:
        raise ValueError("Artifact Principles contains no text to embed")
    return chunks, digest.hexdigest()


def build_principle_contexts(embedder, artifacts: list[ArtifactDefinition]) -> dict[str, dict[str, Any]]:
    chunks, corpus_hash = _corpus()
    manifest_path = CACHE_DIR / "manifest.json"
    current = False
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            current = manifest.get("corpus_sha256") == corpus_hash and manifest.get("embedding_model") == EMBEDDING_MODEL
        except (OSError, json.JSONDecodeError):
            current = False
    if current:
        vectors = np.load(CACHE_DIR / "embeddings.npy")
        cached = [json.loads(line) for line in (CACHE_DIR / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line]
        if vectors.shape[0] != len(cached):
            current = False
        else:
            chunks = cached
    if not current:
        vectors = np.asarray(list(embedder.passage_embed([item["text"] for item in chunks], batch_size=32)), dtype=np.float32)
        vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        np.save(CACHE_DIR / "embeddings.npy", vectors)
        (CACHE_DIR / "chunks.jsonl").write_text(
            "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in chunks), encoding="utf-8"
        )
        manifest = {
            "corpus_sha256": corpus_hash,
            "embedding_model": EMBEDDING_MODEL,
            "number_of_chunks": len(chunks),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    contexts: dict[str, dict[str, Any]] = {}
    for artifact in artifacts:
        query = (
            f"{artifact.name} {artifact.key}. Best practices for deciding whether definitions are equivalent, "
            "whether artifacts should be merged, reused, constrained, or split, and how to preserve all "
            "statistical meanings, units, populations, versions, metadata attachments, and SDMX structures."
        )
        relevant = retrieve(embedder, vectors, chunks, query)
        own = [item for item in chunks if item["source_filename"] == artifact.path.name]
        selected = {item["chunk_id"]: item for item in [*relevant, *own]}
        ordered = [selected[key] for key in sorted(selected)]
        contexts[artifact.key] = {
            "corpus_sha256": corpus_hash,
            "chunk_ids": [item["chunk_id"] for item in ordered],
            "text": "\n\n".join(
                f"<<<BEST_PRACTICE:{item['chunk_id']} SOURCE:{item['source_filename']}>>>\n{item['text']}" for item in ordered
            ),
        }
    return contexts
