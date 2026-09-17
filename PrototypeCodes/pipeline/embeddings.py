from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from fastembed import TextEmbedding

from .config import CHUNK_CHARS, CHUNK_OVERLAP, CHUNKER_VERSION, EMBEDDING_MODEL, MODEL_CACHE, RETRIEVAL_TOP_K


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def make_chunks(text: str, source_name: str) -> list[dict[str, Any]]:
    blocks = [block for block in re.split(r"(?=\n\[(?:PAGE|SECTION|TABLE|FOOTNOTE|WORKSHEET|SLIDE|PARAGRAPH|TEXT)[^\]]*\])", text) if block.strip()]
    chunks: list[dict[str, Any]] = []
    cursor = 0
    index = 0
    while index < len(blocks):
        selected: list[str] = []
        size = 0
        start_index = index
        while index < len(blocks) and (not selected or size + len(blocks[index]) <= CHUNK_CHARS):
            selected.append(blocks[index])
            size += len(blocks[index])
            index += 1
        value = "".join(selected).strip()
        start = text.find(value[: min(80, len(value))], cursor) if value else cursor
        start = cursor if start < 0 else start
        end = start + len(value)
        markers = re.findall(r"\[([^\]]+)\]", value)
        page = next((m for m in markers if m.startswith("PAGE ")), None)
        section = next((m for m in markers if m in {"SECTION", "PARAGRAPH"}), None)
        table = next((m for m in markers if m.startswith("TABLE")), None)
        chunks.append({"chunk_id": len(chunks) + 1, "source_filename": source_name, "text": value, "start_char": start, "end_char": end, "page": page, "section": section, "table": table})
        cursor = end
        if index < len(blocks) and selected:
            overlap = 0
            rewind = index
            while rewind > start_index and overlap < CHUNK_OVERLAP:
                rewind -= 1
                overlap += len(blocks[rewind])
            index = max(start_index + 1, rewind)
    return chunks


def embed_and_save(text: str, source_name: str, source_hash: str, output_dir: Path, embedder: TextEmbedding) -> tuple[np.ndarray, list[dict[str, Any]]]:
    chunks = make_chunks(text, source_name)
    if not chunks:
        raise ValueError("TXT produced no chunks")
    vectors = np.asarray(list(embedder.passage_embed([item["text"] for item in chunks], batch_size=32)), dtype=np.float32)
    if vectors.ndim != 2 or vectors.shape[0] != len(chunks):
        raise ValueError(f"Unexpected embedding shape: {vectors.shape}")
    vectors /= np.maximum(np.linalg.norm(vectors, axis=1, keepdims=True), 1e-12)
    output_dir.mkdir(parents=True, exist_ok=True)
    np.save(output_dir / "embeddings.npy", vectors)
    with (output_dir / "chunks.jsonl").open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in chunks:
            handle.write(json.dumps(chunk, ensure_ascii=False) + "\n")
    manifest = {
        "source_filename": source_name, "source_hash": source_hash, "txt_hash": sha256_text(text),
        "embedding_model": EMBEDDING_MODEL, "embedding_dimension": int(vectors.shape[1]),
        "number_of_chunks": len(chunks), "chunk_chars": CHUNK_CHARS, "chunk_overlap": CHUNK_OVERLAP,
        "chunker_version": CHUNKER_VERSION, "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return vectors, chunks


def load_embeddings(output_dir: Path) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, Any]]:
    vectors = np.load(output_dir / "embeddings.npy")
    chunks = [json.loads(line) for line in (output_dir / "chunks.jsonl").read_text(encoding="utf-8").splitlines() if line]
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    if vectors.shape[0] != len(chunks) or manifest["number_of_chunks"] != len(chunks):
        raise ValueError("Embedding cache count mismatch")
    return vectors, chunks, manifest


def retrieve(embedder: TextEmbedding, vectors: np.ndarray, chunks: list[dict[str, Any]], query: str) -> list[dict[str, Any]]:
    query_vector = np.asarray(list(embedder.query_embed([query])), dtype=np.float32)[0]
    query_vector /= max(float(np.linalg.norm(query_vector)), 1e-12)
    scores = vectors @ query_vector
    count = min(RETRIEVAL_TOP_K, len(chunks))
    ranked = list(np.argsort(-scores)[:count])
    selected = set(int(i) for i in ranked)
    for item in ranked:
        selected.update(i for i in (int(item) - 1, int(item) + 1) if 0 <= i < len(chunks))
    return [{**chunks[i], "similarity": round(float(scores[i]), 6)} for i in sorted(selected)]


def build_embedder() -> TextEmbedding:
    snapshots = MODEL_CACHE / "models--qdrant--bge-base-en-v1.5-onnx-q" / "snapshots"
    local_models = sorted(snapshots.glob("*/model_optimized.onnx")) if snapshots.exists() else []
    if EMBEDDING_MODEL == "BAAI/bge-base-en-v1.5" and local_models:
        return TextEmbedding(
            model_name=EMBEDDING_MODEL,
            cache_dir=str(MODEL_CACHE),
            specific_model_path=str(local_models[0].parent),
        )
    return TextEmbedding(model_name=EMBEDDING_MODEL, cache_dir=str(MODEL_CACHE))
