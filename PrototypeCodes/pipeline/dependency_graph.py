from __future__ import annotations

import hashlib
import json
from typing import Any

from .artifacts import artifact_folder_name
from .config import ARTIFACT_ROOT


DEPENDENCIES = {
    "DSD_KEY_FAMILY": ["CONCEPT_SCHEME", "CODELISTS"],
    "DATAFLOW": ["DSD_KEY_FAMILY"],
    "METADATA_STRUCTURE_DEFINITION_MSD": ["CONCEPT_SCHEME", "DATAFLOW"],
    "METADATA_SET": ["METADATA_STRUCTURE_DEFINITION_MSD", "DATAFLOW", "DSD_KEY_FAMILY"],
    "AI_FILLABLE_DATA_TEMPLATE": ["DSD_KEY_FAMILY", "CODELISTS"],
    "CODEBOOK_AND_SOURCE_MAPPING": [
        "CONCEPT_SCHEME", "CODELISTS", "DSD_KEY_FAMILY", "DATAFLOW",
        "METADATA_STRUCTURE_DEFINITION_MSD",
    ],
}

ARTIFACT_ORDER = [
    "CONCEPT_SCHEME", "CODELISTS", "DSD_KEY_FAMILY", "DATAFLOW",
    "METADATA_STRUCTURE_DEFINITION_MSD", "METADATA_SET",
    "AI_FILLABLE_DATA_TEMPLATE", "CODEBOOK_AND_SOURCE_MAPPING",
]

AUTHORITY_HIERARCHY = """Authority hierarchy for conflict repair:
1. Concept Scheme and Codelists are authoritative for semantic definitions and controlled values.
2. DSD is authoritative for structural IDs, dimensions, measures, attributes, and their representations.
3. Dataflow must reference an existing accepted DSD and cannot rename it.
4. MSD is authoritative for metadata concepts.
5. Metadata Set must use accepted MSD and Dataflow IDs exactly.
6. AI-fillable templates must use accepted DSD IDs and structures exactly.
7. Codebook mappings must target their declared fields and conform to accepted concepts, codelists, DSDs, and dataflows.
When two artifacts disagree, repair the lower item in this hierarchy; do not silently rename the higher authority."""


def dependency_material(artifact_key: str, stem: str) -> tuple[str, str, dict[str, dict[str, Any]]]:
    texts: list[str] = []
    hashes: list[str] = []
    values: dict[str, dict[str, Any]] = {}
    for key in DEPENDENCIES.get(artifact_key, []):
        path = ARTIFACT_ROOT / artifact_folder_name(key) / f"{stem}.json"
        if path.exists():
            text = path.read_text(encoding="utf-8")
            texts.append(f"\n===== ACCEPTED AUTHORITATIVE ARTIFACT: {key} =====\n{text}")
            hashes.append(hashlib.sha256(text.encode("utf-8")).hexdigest())
            values[key] = json.loads(text)
    return "".join(texts), "|".join(hashes), values
