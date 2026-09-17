from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from .agents import optimize_until_approved
from .artifacts import ArtifactDefinition, artifact_folder_name
from .config import AGGREGATE_BATCH_SIZE, ARTIFACT_ROOT, MAX_AGGREGATE_RETRIES, ROOT
from .control import ControlWorkbook, now
from .csv_companion import csv_to_value, json_to_csv, mtime_ns, write_json_atomic
from .models import model_for


def _json_hash(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _path_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_envelope(value: Any, artifact: ArtifactDefinition, model: type[BaseModel]) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("Aggregate JSON must be an object")
    required = {
        "artifact_key", "artifact_name", "principles_file", "principles_sha256",
        "principles_corpus_sha256", "best_practice_chunk_ids",
        "aggregate_version", "created_at", "updated_at", "update_mode",
        "contributions", "optimizer_attempts", "inspector_review", "optimized_artifact",
        "validator_direct_correction",
    }
    missing = sorted(required - set(value))
    if missing:
        raise ValueError(f"Aggregate envelope is missing fields: {', '.join(missing)}")
    if value["artifact_key"] != artifact.key or value["principles_sha256"] != artifact.sha256:
        raise ValueError("Aggregate artifact key or principles hash is stale")
    if not isinstance(value["contributions"], list):
        raise ValueError("Aggregate contributions must be a list")
    seen = set()
    for contribution in value["contributions"]:
        if not isinstance(contribution, dict) or not {"source_report", "source_json_path", "json_sha256"}.issubset(contribution):
            raise ValueError("Invalid aggregate contribution record")
        if contribution["source_report"] in seen:
            raise ValueError("Duplicate aggregate source report")
        seen.add(contribution["source_report"])
    model.model_validate(value["optimized_artifact"])
    return value


def _sync_aggregate_companion(
    control: ControlWorkbook,
    artifact: ArtifactDefinition,
    json_path: Path,
    csv_path: Path,
    model: type[BaseModel],
) -> tuple[dict[str, Any] | None, bool]:
    if not json_path.exists():
        return None, False
    recorded_json = control.aggregate_get(artifact.key, "JSON_MTIME_NS")
    recorded_csv = control.aggregate_get(artifact.key, "CSV_MTIME_NS")
    json_changed = recorded_json is not None and str(recorded_json) != mtime_ns(json_path)
    csv_changed = csv_path.exists() and recorded_csv is not None and str(recorded_csv) != mtime_ns(csv_path)
    modified = False
    try:
        if csv_changed and (not json_changed or csv_path.stat().st_mtime_ns >= json_path.stat().st_mtime_ns):
            value = _validate_envelope(csv_to_value(csv_path), artifact, model)
            write_json_atomic(json_path, value)
            json_to_csv(json_path, csv_path)
            modified = True
        else:
            value = _validate_envelope(json.loads(json_path.read_text(encoding="utf-8")), artifact, model)
            if json_changed:
                json_to_csv(json_path, csv_path)
                modified = True
            elif not csv_path.exists() or recorded_csv is None:
                json_to_csv(json_path, csv_path)
        control.aggregate_set(artifact.key, "AGGREGATE_JSON_PATH", str(json_path.relative_to(ROOT)), save=False)
        control.aggregate_set(artifact.key, "AGGREGATE_JSON_HASH", _path_hash(json_path), save=False)
        control.aggregate_set(artifact.key, "JSON_MTIME_NS", mtime_ns(json_path), save=False)
        control.aggregate_set(artifact.key, "CSV_MTIME_NS", mtime_ns(csv_path), save=False)
        if modified:
            control.aggregate_stage(artifact.key, "MODIFIED")
        else:
            control.save()
        return value, modified
    except Exception as error:
        control.aggregate_stage(artifact.key, "FAILED", f"{type(error).__name__}: {error}")
        raise


def _candidate_rows(control: ControlWorkbook, artifact: ArtifactDefinition, model: type[BaseModel]) -> tuple[list[dict[str, Any]], list[int]]:
    candidates = []
    unavailable = []
    for row in control.data_rows():
        status = control.get(row, f"{artifact.key}_STATUS")
        path_value = control.get(row, f"{artifact.key}_JSON_PATH")
        if status not in {"SUCCESS", "MODIFIED"} or not path_value:
            control.set(row, f"{artifact.key}_AGGREGATED", "NO", save=False)
            unavailable.append(row)
            continue
        path = ROOT / str(path_value)
        try:
            value = model.model_validate_json(path.read_text(encoding="utf-8")).model_dump(mode="json")
        except Exception:
            control.set(row, f"{artifact.key}_AGGREGATED", "NO", save=False)
            unavailable.append(row)
            continue
        digest = _path_hash(path)
        candidates.append({
            "row": row,
            "source_report": str(control.get(row, "FILE_NAME")),
            "source_json_path": str(path.relative_to(ROOT)),
            "json_sha256": digest,
            "artifact": value,
        })
    control.save()
    return candidates, unavailable


def _save_checkpoint(
    control: ControlWorkbook,
    artifact: ArtifactDefinition,
    json_path: Path,
    csv_path: Path,
    envelope: dict[str, Any],
    contribution_rows: dict[str, dict[str, Any]],
    all_ready: bool,
) -> None:
    write_json_atomic(json_path, envelope)
    json_to_csv(json_path, csv_path)
    aggregate_hash = _path_hash(json_path)
    control.aggregate_set(artifact.key, "ARTIFACT_NAME", artifact.name, save=False)
    control.aggregate_set(artifact.key, "AGGREGATE_JSON_PATH", str(json_path.relative_to(ROOT)), save=False)
    control.aggregate_set(artifact.key, "AGGREGATE_JSON_HASH", aggregate_hash, save=False)
    control.aggregate_set(artifact.key, "JSON_MTIME_NS", mtime_ns(json_path), save=False)
    control.aggregate_set(artifact.key, "CSV_MTIME_NS", mtime_ns(csv_path), save=False)
    control.aggregate_set(artifact.key, "CONTRIBUTION_COUNT", len(envelope["contributions"]), save=False)
    control.aggregate_set(artifact.key, "PRINCIPLES_HASH", artifact.sha256, save=False)
    accepted = {item["source_report"]: item["json_sha256"] for item in envelope["contributions"]}
    for source_report, item in contribution_rows.items():
        included = accepted.get(source_report) == item["json_sha256"]
        control.set(item["row"], f"{artifact.key}_AGGREGATED", "YES" if included else "NO", save=False)
        control.set(item["row"], f"{artifact.key}_AGGREGATED_JSON_HASH", item["json_sha256"] if included else "", save=False)
        control.set(item["row"], f"{artifact.key}_AGGREGATED_LAST_RUN", now() if included else "", save=False)
    control.aggregate_stage(artifact.key, "SUCCESS" if all_ready else "PENDING", "" if all_ready else "Some report artifacts are not ready for aggregation")


def run_aggregation_stage(
    artifacts: list[ArtifactDefinition],
    control: ControlWorkbook,
    client,
    settings: dict[str, str],
    principle_contexts: dict[str, dict[str, Any]],
) -> None:
    print("\nAggregate optimization stage")
    for artifact in artifacts:
        model = model_for(artifact.key)
        folder = ARTIFACT_ROOT / artifact_folder_name(artifact.key)
        json_path = folder / "_aggregate.json"
        csv_path = folder / "_aggregate.csv"
        try:
            principles = principle_contexts[artifact.key]
            stale_principles = False
            if json_path.exists():
                try:
                    saved = json.loads(json_path.read_text(encoding="utf-8"))
                    stale_principles = (
                        saved.get("principles_sha256") != artifact.sha256
                        or saved.get("principles_corpus_sha256") != principles["corpus_sha256"]
                    )
                except (OSError, json.JSONDecodeError, AttributeError):
                    stale_principles = False
            if stale_principles:
                envelope, aggregate_modified = None, False
                control.aggregate_stage(artifact.key, "PENDING", "Artifact principles changed; aggregate rebuild required")
            else:
                envelope, aggregate_modified = _sync_aggregate_companion(control, artifact, json_path, csv_path, model)
            candidates, unavailable = _candidate_rows(control, artifact, model)
            candidate_by_source = {item["source_report"]: item for item in candidates}
            previous = {item["source_report"]: item for item in envelope["contributions"]} if envelope else {}
            changed = [
                item for item in candidates
                if previous.get(item["source_report"], {}).get("json_sha256") != item["json_sha256"]
                or control.get(item["row"], f"{artifact.key}_AGGREGATED") != "YES"
                or control.get(item["row"], f"{artifact.key}_AGGREGATED_JSON_HASH") != item["json_sha256"]
            ]
            if not changed:
                all_ready = not unavailable and len(candidates) == len(control.data_rows())
                if envelope is None:
                    control.aggregate_stage(artifact.key, "PENDING", "No completed report artifacts are available")
                    print(f"  {artifact.key}: PENDING (no completed inputs)")
                else:
                    for item in candidates:
                        included = previous.get(item["source_report"], {}).get("json_sha256") == item["json_sha256"]
                        control.set(item["row"], f"{artifact.key}_AGGREGATED", "YES" if included else "NO", save=False)
                        control.set(item["row"], f"{artifact.key}_AGGREGATED_JSON_HASH", item["json_sha256"] if included else "", save=False)
                        control.set(item["row"], f"{artifact.key}_AGGREGATED_LAST_RUN", now() if included else "", save=False)
                    if aggregate_modified:
                        control.aggregate_stage(artifact.key, "MODIFIED", "" if all_ready else "Some report artifacts are not ready for aggregation")
                    else:
                        control.aggregate_stage(artifact.key, "SUCCESS" if all_ready else "PENDING", "" if all_ready else "Some report artifacts are not ready for aggregation")
                    print(f"  {artifact.key}: SKIPPED (aggregate current; {len(previous)} contributions)")
                continue

            for start in range(0, len(changed), AGGREGATE_BATCH_SIZE):
                batch = changed[start:start + AGGREGATE_BATCH_SIZE]
                contribution_map = dict(previous)
                for item in batch:
                    contribution_map[item["source_report"]] = {
                        "source_report": item["source_report"],
                        "source_json_path": item["source_json_path"],
                        "json_sha256": item["json_sha256"],
                    }
                expected_sources = sorted(contribution_map)
                aggregate_source_hash = hashlib.sha256(
                    "|".join(f"{name}:{contribution_map[name]['json_sha256']}" for name in expected_sources).encode("utf-8")
                ).hexdigest()
                control.aggregate_stage(artifact.key, "RUNNING")
                candidate, review, attempts = optimize_until_approved(
                    client, settings, artifact, model, aggregate_source_hash,
                    envelope["optimized_artifact"] if envelope else None,
                    [{key: value for key, value in item.items() if key != "row"} for item in batch],
                    expected_sources,
                    principles["text"],
                    principles["chunk_ids"],
                )
                timestamp = datetime.now(timezone.utc).isoformat()
                envelope = {
                    "artifact_key": artifact.key,
                    "artifact_name": artifact.name,
                    "principles_file": artifact.path.name,
                    "principles_sha256": artifact.sha256,
                    "principles_corpus_sha256": principles["corpus_sha256"],
                    "best_practice_chunk_ids": principles["chunk_ids"],
                    "aggregate_version": (int(envelope["aggregate_version"]) + 1) if envelope else 1,
                    "created_at": envelope["created_at"] if envelope else timestamp,
                    "updated_at": timestamp,
                    "update_mode": "INCREMENTAL" if previous else "INITIAL",
                    "contributions": [contribution_map[name] for name in expected_sources],
                    "optimizer_attempts": attempts,
                    "validator_direct_correction": attempts > MAX_AGGREGATE_RETRIES,
                    "inspector_review": review.model_dump(mode="json"),
                    "optimized_artifact": candidate.model_dump(mode="json"),
                }
                previous = contribution_map
                ready_after_batch = not unavailable and len(previous) == len(control.data_rows())
                _save_checkpoint(control, artifact, json_path, csv_path, envelope, candidate_by_source, ready_after_batch)
                print(f"  {artifact.key}: approved batch {start // AGGREGATE_BATCH_SIZE + 1} ({len(batch)} new/changed; {len(previous)} total)")
            all_ready = not unavailable and len(previous) == len(control.data_rows())
            control.aggregate_stage(artifact.key, "SUCCESS" if all_ready else "PENDING", "" if all_ready else "Some report artifacts are not ready for aggregation")
        except Exception as error:
            control.aggregate_stage(artifact.key, "FAILED", f"{type(error).__name__}: {error}")
            print(f"  {artifact.key}: FAILED ({type(error).__name__}: {error})")
