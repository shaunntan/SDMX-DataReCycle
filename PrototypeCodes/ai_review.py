#!/usr/bin/env python3
"""Codex-backed metadata review for the web app's Review Metadata flow.

Reads a JSON payload from stdin shaped like:
    {"artifact_type": "codelist" | "conceptscheme" | "dsd" | "dataflow",
     "artifact_identity": {<ArtifactIdentity>},
     "items": [<ReviewItem>, ...],
     "prompt_override": str (optional; used verbatim instead of the template),
     "dry_run": bool (optional; print {"prompt", "unavailable"} without
                calling codex, so the UI can show/edit the prompt first)}

Asks Codex (via pipeline.agents.call_structured, the same strict-JSON path
the pipeline uses) to propose field-level changes for those review items,
using the system prompt in prompts/metadata_review_system_prompt.txt.

Prints one JSON object to stdout: {"changes": [<SuggestedChange>, ...],
"unavailable": bool}. It never raises past main(): the web route treats an
"unavailable" result as "fall back to placeholder suggestions", so a missing
codex CLI or a failed call must degrade rather than fail the request.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic import BaseModel  # noqa: E402

from pipeline.agents import call_structured, load_client  # noqa: E402
from pipeline.config import CODEX_BIN  # noqa: E402

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "metadata_review_system_prompt.txt"
REVIEWABLE_TYPES = {"codelist", "conceptscheme", "dsd"}


class MetadataChange(BaseModel):
    change_id: str
    item_id: str
    field: str
    current_value: str | None = None
    suggested_value: str | None = None
    rationale: str


class MetadataReviewResponse(BaseModel):
    changes: list[MetadataChange]


def build_prompt(artifact_type: str, identity: dict[str, Any], items: list[dict[str, Any]]) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{artifact_type}", artifact_type)
        .replace("{artifact_identity_json}", json.dumps(identity, ensure_ascii=False, indent=2))
        .replace("{items_json}", json.dumps(items, ensure_ascii=False, indent=2))
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        artifact_type = str(payload.get("artifact_type") or "")
        identity = payload.get("artifact_identity") or {}
        items = payload.get("items") or []
        prompt_override = payload.get("prompt_override") or ""
        dry_run = bool(payload.get("dry_run"))

        if artifact_type not in REVIEWABLE_TYPES:
            if dry_run:
                # Nothing would be built or sent, so there is no prompt to show.
                print(json.dumps({
                    "prompt": None,
                    "unavailable": False,
                    "note": "Dataflow review conventions are not yet defined; no automated suggestions.",
                }))
                return 0
            # sdmx/review_requirements.md doesn't define dataflow review
            # conventions, so there's nothing to ask Codex for here.
            print(json.dumps({
                "changes": [],
                "unavailable": False,
                "note": "Dataflow review conventions are not yet defined; no automated suggestions.",
            }))
            return 0

        prompt = prompt_override or build_prompt(artifact_type, identity, items)

        if dry_run:
            # "Show me the prompt first": build it, but never call codex.
            print(json.dumps({"prompt": prompt, "unavailable": not CODEX_BIN}))
            return 0

        if not CODEX_BIN:
            print(json.dumps({"changes": [], "unavailable": True}))
            return 0

        client, settings = load_client()
        value = call_structured(
            client, settings, prompt, MetadataReviewResponse, "metadata_review",
        )
        response = MetadataReviewResponse.model_validate(value)
        artifact_id = str(identity.get("artifact_id") or "")
        changes = [
            {**change.model_dump(), "artifact_type": artifact_type, "artifact_id": artifact_id}
            for change in response.changes
        ]
        print(json.dumps({"changes": changes, "unavailable": False}))
        return 0
    except Exception as error:  # never crash the web request
        print(json.dumps({
            "changes": [],
            "unavailable": True,
            "error": f"{type(error).__name__}: {error}"[-500:],
        }))
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
