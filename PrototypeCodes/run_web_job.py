#!/usr/bin/env python3
"""Thin wrapper around run_pipeline.py for the Next.js Upload flow.

Runs the real pipeline for a single uploaded file, limited to the artifact
types the web app currently knows how to display in Metadata Review
(CONCEPT_SCHEME, CODELISTS, DSD_KEY_FAMILY, DATAFLOW -- the other 4 real
artifact types are intentionally out of scope for the frontend today), then
runs the Codex-driven Parquet conversion (run_data_conversion.py) for each
DSD structure produced. Writes JSON progress to --status-file so a Next.js
API route can poll it.

Every generation attempt (the automatic one, and any manual retries done via
run_manual_retry.py) is recorded under status["attempts"][KEY] with its
prompt, so the web app can show/edit/retry it and pick which attempt to use.
On the FIRST failure of a required step, the job stops (phase=NEEDS_INPUT)
instead of failing outright -- run_manual_retry.py or the select-attempt
route can resolve that step and call run_steps(..., resume=True) to continue
without redoing already-successful steps.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

WEB_ARTIFACT_KEYS = ["CONCEPT_SCHEME", "CODELISTS", "DSD_KEY_FAMILY", "DATAFLOW"]


def write_status(status_path: Path, status: dict) -> None:
    status["updated_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    tmp = status_path.with_suffix(".tmp")
    tmp.write_text(json.dumps(status, indent=2), encoding="utf-8")
    tmp.replace(status_path)


def attempts_dir(status_path: Path) -> Path:
    d = status_path.parent / "attempts"
    d.mkdir(parents=True, exist_ok=True)
    return d


def record_attempt(
    status: dict, status_path: Path, key: str, source: str, prompt: str | None,
    ok: bool, error: str | None, output: dict[str, Any] | None,
) -> int:
    status.setdefault("attempts", {}).setdefault(key, [])
    attempt_id = len(status["attempts"][key])
    entry: dict[str, Any] = {
        "id": attempt_id, "source": source, "prompt": prompt,
        "status": "SUCCESS" if ok else "FAILED", "error": error,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    if ok and output is not None:
        out_path = attempts_dir(status_path) / f"{key}_{attempt_id}.json"
        out_path.write_text(json.dumps(output), encoding="utf-8")
    status["attempts"][key].append(entry)
    write_status(status_path, status)
    return attempt_id


def promote_attempt(status: dict, status_path: Path, key: str, attempt_id: int, artifact_root: Path, folder_name, stem: str) -> None:
    out_path = attempts_dir(status_path) / f"{key}_{attempt_id}.json"
    canonical = artifact_root / folder_name(key) / f"{stem}.json"
    canonical.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(out_path, canonical)
    status["steps"][key] = "SUCCESS"
    status.setdefault("selected_attempt", {})[key] = attempt_id
    write_status(status_path, status)


def next_pending_key(status: dict) -> str | None:
    for key in WEB_ARTIFACT_KEYS:
        if status["steps"].get(key) != "SUCCESS":
            return key
    return None


def run_steps(args_file: str, status: dict, status_path: Path) -> int:
    """Advances the job from wherever `status["steps"]` says it left off."""
    import run_pipeline
    from pipeline.artifacts import artifact_folder_name
    from pipeline.config import ARTIFACT_ROOT, TEXT_ROOT
    from run_data_conversion import DATA_CONVERSIONS_ROOT, convert_one

    stem = status["stem"]
    prompt_scratch = status_path.parent / "prompt_scratch"

    while True:
        key = next_pending_key(status)
        if key is None:
            break
        status["steps"][key] = "RUNNING"
        status["phase"] = "RUNNING"
        write_status(status_path, status)

        if prompt_scratch.exists():
            shutil.rmtree(prompt_scratch)
        os.environ["SDMX_PROMPT_LOG_DIR"] = str(prompt_scratch)

        sys.argv = ["run_pipeline.py", "--skip-aggregate", "--file", args_file, "--artifact", key]
        crashed_error = None
        try:
            run_pipeline.main()
        except Exception as error:
            crashed_error = f"{type(error).__name__}: {error}"

        prompt_file = prompt_scratch / f"{key}.txt"
        prompt_text = prompt_file.read_text(encoding="utf-8") if prompt_file.exists() else None

        output_path = ARTIFACT_ROOT / artifact_folder_name(key) / f"{stem}.json"
        if crashed_error is None and output_path.exists():
            output = json.loads(output_path.read_text(encoding="utf-8"))
            attempt_id = record_attempt(status, status_path, key, "auto", prompt_text, True, None, output)
            status.setdefault("selected_attempt", {})[key] = attempt_id
            status["steps"][key] = "SUCCESS"
            write_status(status_path, status)
        else:
            error_message = crashed_error or f"{key}: no output artifact was produced"
            record_attempt(status, status_path, key, "auto", prompt_text, False, error_message, None)
            status["steps"][key] = "FAILED"
            status["phase"] = "NEEDS_INPUT"
            status["error"] = error_message
            write_status(status_path, status)
            return 0  # recoverable pause, not a hard failure

    # All 4 metadata steps are SUCCESS: data conversion, one Codex-authored
    # script + Parquet file per DSD structure. No automatic retry here either
    # -- failures (and whatever script Codex wrote, if any) are surfaced as-is.
    dsd_path = ARTIFACT_ROOT / artifact_folder_name("DSD_KEY_FAMILY") / f"{stem}.json"
    text_path = TEXT_ROOT / f"{stem}.txt"
    dsd_data = json.loads(dsd_path.read_text(encoding="utf-8"))
    report_text = text_path.read_text(encoding="utf-8")
    status.setdefault("data_conversion", {})
    for dsd in dsd_data.get("data_structures", []):
        dsd_id = dsd.get("dsd_id", "UNKNOWN_DSD")
        if status["data_conversion"].get(dsd_id, {}).get("status") == "SUCCESS":
            continue
        status["data_conversion"][dsd_id] = {"status": "RUNNING"}
        write_status(status_path, status)
        dest_dir = DATA_CONVERSIONS_ROOT / f"{stem}__{dsd_id}"
        result = convert_one(dsd, report_text, dest_dir)
        status["data_conversion"][dsd_id] = {"status": result["status"], "error": result.get("error")}
        write_status(status_path, status)

    status["phase"] = "DONE"
    status["error"] = None
    write_status(status_path, status)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Filename relative to Inputs/")
    parser.add_argument("--status-file", required=True)
    parser.add_argument("--resume", action="store_true", help="Continue an existing status file")
    args = parser.parse_args()

    status_path = Path(args.status_file)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    stem = Path(args.file).stem

    if args.resume and status_path.exists():
        status = json.loads(status_path.read_text(encoding="utf-8"))
    else:
        status = {
            "file": args.file, "stem": stem, "phase": "RUNNING",
            "steps": {key: "PENDING" for key in WEB_ARTIFACT_KEYS},
            "attempts": {}, "selected_attempt": {}, "data_conversion": {}, "error": None,
        }
        write_status(status_path, status)

    return run_steps(args.file, status, status_path)


if __name__ == "__main__":
    raise SystemExit(main())
