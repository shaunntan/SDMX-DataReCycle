#!/usr/bin/env python3
"""Structural validity check for the web app's Export flow.

Reads a JSON payload from stdin shaped like:
    {"conceptscheme": [<ConceptScheme obj>, ...],
     "codelist": [<Codelist obj>, ...],
     "dsd": [<DataStructure obj>, ...]}

Each array holds the RECONSTRUCTED single-artifact objects the web app
built (web/src/lib/reconstructArtifact.ts) -- i.e. the pipeline's own real
extracted objects with the curator's reviewed fields (name/definition, or
role/codelist_id/usage_status/data_type) and confirmed identity
(agency_id/version/name) overlaid on top.

This wraps each group in a minimal-but-valid envelope (the BaseArtifact
provenance fields aren't meaningful for an export-time structural check, so
they're filled with placeholders) and validates it against the REAL
Pydantic schemas in pipeline/models.py -- the same schemas the pipeline
itself enforces when generating these artifacts. Prints one JSON object to
stdout: {"conceptscheme": {"valid": bool, "errors": [str, ...]}, ...}.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic import ValidationError  # noqa: E402

from pipeline.models import CodelistsArtifact, ConceptSchemeArtifact, DataflowArtifact, DSDArtifact  # noqa: E402

PLACEHOLDER_SHA256 = hashlib.sha256(b"export-consistency-check").hexdigest()

GROUPS: dict[str, tuple[type, str]] = {
    "conceptscheme": (ConceptSchemeArtifact, "concept_schemes"),
    "codelist": (CodelistsArtifact, "codelists"),
    "dsd": (DSDArtifact, "data_structures"),
    "dataflow": (DataflowArtifact, "dataflows"),
}


def envelope_for(key: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    base = {
        "artifact_type": key.upper(),
        "source_report": "EXPORT_CONSISTENCY_CHECK",
        "source_sha256": PLACEHOLDER_SHA256,
        "principles_file": "export_check",
        "principles_sha256": PLACEHOLDER_SHA256,
        "retrieved_chunk_ids": [],
        "standard_references": [],
        "limitations": [],
    }
    _, field = GROUPS[key]
    base[field] = items
    if key == "dsd":
        base["structure_separation_rationale"] = "Not applicable: export-time structural check."
    return base


def main() -> int:
    payload = json.loads(sys.stdin.read() or "{}")
    result: dict[str, Any] = {}
    for key, (model, _field) in GROUPS.items():
        items = payload.get(key) or []
        if not items:
            result[key] = {"valid": True, "errors": []}
            continue
        try:
            model.model_validate(envelope_for(key, items))
            result[key] = {"valid": True, "errors": []}
        except ValidationError as error:
            errors = [f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in error.errors()]
            result[key] = {"valid": False, "errors": errors}
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
