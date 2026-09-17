from __future__ import annotations

import os
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INPUTS = ROOT / "Inputs"
TEXT_ROOT = ROOT / "Inputs_TXT"
EMBEDDING_ROOT = ROOT / "Inputs_Embeddings"
ARTIFACT_ROOT = ROOT / "Artifact JSON"
# Delivered as "ArtifactPrinciples" (no space) at the repo root.
PRINCIPLES_ROOT = ROOT / "ArtifactPrinciples"
CONTROL_FILE = ROOT / "pipeline_control.xlsx"
# This package ships its own bundled model_cache/ and cache/standards/ (see the
# PrototypeCodes/ folder contents) rather than living under a separate top-level
# "Codes" folder, so CODE_ROOT resolves to this package's own directory.
CODE_ROOT = Path(__file__).resolve().parents[1]
MODEL_CACHE = CODE_ROOT / "model_cache"
STANDARD_CACHE = CODE_ROOT / "cache" / "standards"


def _find_codex_bin() -> str | None:
    """Locate a working `codex` CLI binary.

    On this machine the copy on PATH can lag behind the one bundled with the
    ChatGPT desktop app, and an outdated CLI silently defaults to a model the
    account's ChatGPT-auth session isn't allowed to use. Prefer the app-bundled
    binary (or an explicit override) before falling back to PATH.
    """
    override = os.getenv("SDMX_CODEX_BIN")
    if override and Path(override).exists():
        return override
    bundled = Path("/Applications/ChatGPT.app/Contents/Resources/codex")
    if bundled.exists():
        return str(bundled)
    return shutil.which("codex")


CODEX_BIN = _find_codex_bin()
CODEX_CALL_TIMEOUT = int(os.getenv("SDMX_CODEX_TIMEOUT", "1800"))


def prompt_log_dir() -> Path | None:
    """When set (by run_web_job.py, per step, before each generation call),
    the first-attempt generation prompt for the current artifact key is
    written to "<dir>/<KEY>.txt" so the web app can show/edit/retry it. Read
    fresh on every call (not a module-level constant) since run_web_job.py
    changes this env var per step, after pipeline.agents is already imported.
    None in normal CLI use.
    """
    value = os.getenv("SDMX_PROMPT_LOG_DIR")
    return Path(value) if value else None

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
