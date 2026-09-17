#!/usr/bin/env python3
"""Retries ONE artifact-type generation with a user-edited prompt.

Reads the prompt from stdin (avoids argv length limits -- these prompts can
be several KB). Unlike the automatic pipeline, this is a single generate +
Pydantic-validate call: no semantic-review loop, no auto-retry. On success
the result is recorded as a new attempt AND immediately promoted to the
canonical artifact file, then the job is resumed in case this unblocks later
steps (Dataflow depends on DSD, e.g.). On failure the attempt is recorded
with its error and nothing else changes -- the user decides whether to edit
the prompt again or select a different stored attempt instead.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pydantic import ValidationError  # noqa: E402

from pipeline.agents import call_structured, load_client  # noqa: E402
from pipeline.artifacts import artifact_folder_name  # noqa: E402
from pipeline.config import ARTIFACT_ROOT  # noqa: E402
from pipeline.models import model_for  # noqa: E402
from run_web_job import promote_attempt, record_attempt, run_steps  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True)
    parser.add_argument("--artifact", required=True, help="Artifact key, e.g. DSD_KEY_FAMILY")
    parser.add_argument("--status-file", required=True)
    args = parser.parse_args()

    prompt = sys.stdin.read()
    key = args.artifact
    status_path = Path(args.status_file)
    status = json.loads(status_path.read_text(encoding="utf-8"))
    stem = status["stem"]
    model = model_for(key)

    client, settings = load_client()
    try:
        value = call_structured(client, settings, prompt, model, f"manual_retry_{key.lower()}")
        validated = model.model_validate(value)
        output = validated.model_dump(mode="json")
        attempt_id = record_attempt(status, status_path, key, "manual", prompt, True, None, output)
        # Re-read: record_attempt already persisted the write, but keep our
        # in-memory copy in sync before promoting/resuming.
        status = json.loads(status_path.read_text(encoding="utf-8"))
        promote_attempt(status, status_path, key, attempt_id, ARTIFACT_ROOT, artifact_folder_name, stem)
    except (ValidationError, RuntimeError, ValueError) as error:
        record_attempt(status, status_path, key, "manual", prompt, False, f"{type(error).__name__}: {error}", None)
        return 0

    # Continue the job: run_steps() is a no-op past whatever's already done,
    # so this safely picks up any later steps (or data conversion) that were
    # blocked on this one.
    status = json.loads(status_path.read_text(encoding="utf-8"))
    run_steps(args.file, status, status_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
