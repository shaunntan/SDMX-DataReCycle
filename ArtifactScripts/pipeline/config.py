from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "Inputs"
TEXT_ROOT = ROOT / "Inputs_TXT"
EMBEDDING_ROOT = ROOT / "Inputs_Embeddings"
ARTIFACT_ROOT = ROOT / "Artifact JSON"
PRINCIPLES_ROOT = ROOT / "Artifact Principles"
CONTROL_FILE = ROOT / "pipeline_control.xlsx"
CODE_ROOT = ROOT / "Codes"
KEYS_FILE = CODE_ROOT / "config" / "Keys.json"
MODEL_CACHE = CODE_ROOT / "model_cache"
STANDARD_CACHE = CODE_ROOT / "cache" / "standards"

SUPPORTED_EXTENSIONS = {
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".csv", ".txt",
    ".htm", ".html", ".ppt", ".pptx",
}
EMBEDDING_MODEL = os.getenv("SDMX_EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
CHUNK_CHARS = int(os.getenv("SDMX_CHUNK_CHARS", "1800"))
CHUNK_OVERLAP = int(os.getenv("SDMX_CHUNK_OVERLAP", "250"))
RETRIEVAL_TOP_K = int(os.getenv("SDMX_RETRIEVAL_TOP_K", "8"))
MAX_SCHEMA_RETRIES = int(os.getenv("MAX_SCHEMA_RETRIES", "3"))
MAX_SEMANTIC_RETRIES = int(os.getenv("MAX_SEMANTIC_RETRIES", "2"))
MAX_AGGREGATE_RETRIES = int(os.getenv("MAX_AGGREGATE_RETRIES", "2"))
MAX_FINAL_RETRIES = int(os.getenv("MAX_FINAL_RETRIES", "2"))
AGGREGATE_BATCH_SIZE = int(os.getenv("AGGREGATE_BATCH_SIZE", "3"))
MAX_API_ATTEMPTS = int(os.getenv("MAX_API_ATTEMPTS", "6"))
PIPELINE_VERSION = "report_to_sdmx_v3_principles_final"
EXTRACTOR_VERSION = "semantic_text_v1"
CHUNKER_VERSION = "marker_aware_v1"
FINAL_ARTIFACT_ROOT = ROOT / "Final Artifacts"
FINAL_CSV_ROOT = ROOT / "Final CSV Versions of Artifacts"
XML_INPUTS = ROOT / "Inputs XML"
FINAL_SDMX_ROOT = ROOT / "final SMDX structures"


def ensure_directories() -> None:
    for path in (INPUTS, XML_INPUTS, TEXT_ROOT, EMBEDDING_ROOT, ARTIFACT_ROOT, MODEL_CACHE, STANDARD_CACHE, FINAL_ARTIFACT_ROOT, FINAL_CSV_ROOT, FINAL_SDMX_ROOT):
        path.mkdir(parents=True, exist_ok=True)
