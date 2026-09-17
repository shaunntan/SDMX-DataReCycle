#!/usr/bin/env python3
"""Codex-backed "suggested fixes" for the web app's Export consistency check.

Reads a JSON payload from stdin shaped like:
    {"artifact_types": ["dsd", ...],
     "artifacts_json": {"conceptscheme": [...], "codelist": [...],
                        "dsd": [...], "dataflow": [...]},
     "reference_issues": [str, ...],
     "structural_errors": [str, ...],
     "prompt_override": str (optional; used verbatim instead of the template),
     "dry_run": bool (optional; print {"prompt", "unavailable"} without
                calling codex, so the UI can show/edit the prompt first)}

Asks Codex (via pipeline.agents.call_structured) to propose concrete fixes
for exactly those already-found issues, using the system prompt in
prompts/export_fix_suggestions_system_prompt.txt.

Prints one JSON object to stdout: {"changes": [<SuggestedChange>, ...],
"unavailable": bool}. Like ai_review.py it never raises past main() -- the
web route degrades instead of failing the request.
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

PROMPT_PATH = Path(__file__).resolve().parent / "prompts" / "export_fix_suggestions_system_prompt.txt"


class ExportChange(BaseModel):
    change_id: str
    artifact_type: str
    artifact_id: str
    # Artifact-level fixes (e.g. dsd_agency_id on a Dataflow) have no item.
    item_id: str | None = None
    field: str
    current_value: str | None = None
    suggested_value: str | None = None
    rationale: str


class ExportSuggestResponse(BaseModel):
    changes: list[ExportChange]


def build_prompt(payload: dict[str, Any]) -> str:
    template = PROMPT_PATH.read_text(encoding="utf-8")
    return (
        template.replace("{artifact_types}", json.dumps(payload.get("artifact_types") or []))
        .replace("{artifacts_json}", json.dumps(payload.get("artifacts_json") or {}, ensure_ascii=False, indent=2))
        .replace("{reference_issues}", json.dumps(payload.get("reference_issues") or [], ensure_ascii=False, indent=2))
        .replace("{structural_errors}", json.dumps(payload.get("structural_errors") or [], ensure_ascii=False, indent=2))
    )


def main() -> int:
    try:
        payload = json.loads(sys.stdin.read() or "{}")
        reference_issues = payload.get("reference_issues") or []
        structural_errors = payload.get("structural_errors") or []
        prompt_override = payload.get("prompt_override") or ""
        dry_run = bool(payload.get("dry_run"))
        if not reference_issues and not structural_errors:
            if dry_run:
                # Nothing would be built or sent, so there is no prompt to show.
                print(json.dumps({
                    "prompt": None,
                    "unavailable": False,
                    "note": "No issues to suggest fixes for.",
                }))
                return 0
            print(json.dumps({"changes": [], "unavailable": False}))
            return 0

        prompt = prompt_override or build_prompt(payload)

        if dry_run:
            # "Show me the prompt first": build it, but never call codex.
            print(json.dumps({"prompt": prompt, "unavailable": not CODEX_BIN}))
            return 0

        if not CODEX_BIN:
            print(json.dumps({"changes": [], "unavailable": True}))
            return 0

        client, settings = load_client()
        value = call_structured(
            client, settings, prompt, ExportSuggestResponse, "export_fix_suggestions",
        )
        response = ExportSuggestResponse.model_validate(value)
        print(json.dumps({
            "changes": [change.model_dump() for change in response.changes],
            "unavailable": False,
        }))
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
