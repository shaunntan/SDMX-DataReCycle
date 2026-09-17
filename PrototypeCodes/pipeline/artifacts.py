from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path

from .config import PRINCIPLES_ROOT

REFERENCE_MARKERS = ("README", "PACKAGE_MAP", "COMMON_SDMX", "SOURCE_REFERENCE")


@dataclass(frozen=True)
class ArtifactDefinition:
    key: str
    name: str
    path: Path
    text: str
    sha256: str


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _clean_title(text: str, fallback: str) -> str:
    first = next((line.strip() for line in text.splitlines() if line.strip()), fallback)
    return re.sub(r"\s+", " ", first).strip(" =")


def discover_artifacts() -> tuple[list[ArtifactDefinition], str]:
    if not PRINCIPLES_ROOT.is_dir():
        raise FileNotFoundError(f"Missing artifact principles folder: {PRINCIPLES_ROOT}")
    references: list[str] = []
    artifacts: list[ArtifactDefinition] = []
    for path in sorted(PRINCIPLES_ROOT.glob("*.txt")):
        text = path.read_text(encoding="utf-8-sig")
        upper_name = path.stem.upper()
        if any(marker in upper_name for marker in REFERENCE_MARKERS):
            references.append(f"\n===== {path.name} =====\n{text}")
            continue
        raw_key = re.sub(r"^\d+_", "", path.stem)
        key = re.sub(r"[^A-Z0-9]+", "_", raw_key.upper()).strip("_")
        artifacts.append(ArtifactDefinition(key, _clean_title(text, raw_key), path, text, file_hash(path)))
    if not artifacts:
        raise ValueError("No generated artifacts were discovered from Artifact Principles")
    return artifacts, "".join(references)


def artifact_folder_name(key: str) -> str:
    names = {
        "CONCEPT_SCHEME": "Concept Scheme",
        "CODELISTS": "Codelists",
        "DSD_KEY_FAMILY": "DSD Key Family",
        "DATAFLOW": "Dataflow",
        "METADATA_STRUCTURE_DEFINITION_MSD": "Metadata Structure Definition MSD",
        "METADATA_SET": "Metadata Set",
        "AI_FILLABLE_DATA_TEMPLATE": "AI Fillable Data Template",
        "CODEBOOK_AND_SOURCE_MAPPING": "Codebook and Source Mapping",
    }
    return names.get(key, key.replace("_", " ").title())


def safe_stem(path: Path, all_sources: list[Path]) -> str:
    matching = [item for item in all_sources if item.stem.casefold() == path.stem.casefold()]
    if len(matching) == 1:
        return path.stem
    relative = str(path.relative_to(path.parents[len(path.parts) - len(path.anchor.split('\\')) - 1]))
    suffix = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:10]
    return f"{path.stem}_{suffix}"
