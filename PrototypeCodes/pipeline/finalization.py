from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .agents import finalize_until_approved
from .artifacts import ArtifactDefinition, artifact_folder_name
from .config import ARTIFACT_ROOT, FINAL_ARTIFACT_ROOT, FINAL_CSV_ROOT, MAX_FINAL_RETRIES, ROOT
from .control import ControlWorkbook
from .csv_companion import mtime_ns, nice_json_to_csv, write_json_atomic
from .models import final_envelope_model


COLLECTIONS = {
    "CONCEPT_SCHEME": ("concept_schemes", "scheme_id"),
    "CODELISTS": ("codelists", "codelist_id"),
    "DSD_KEY_FAMILY": ("data_structures", "dsd_id"),
    "DATAFLOW": ("dataflows", "dataflow_id"),
    "METADATA_STRUCTURE_DEFINITION_MSD": ("metadata_structures", "msd_id"),
    "METADATA_SET": ("metadata_sets", "metadata_set_id"),
    "AI_FILLABLE_DATA_TEMPLATE": ("templates", "template_id"),
}


def _hash_bytes(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_multiplicity(artifact: ArtifactDefinition, envelope) -> None:
    decision = envelope.multiplicity_decision
    if artifact.key == "CODEBOOK_AND_SOURCE_MAPPING":
        actual_ids = ["CODEBOOK_MAPPING_FINAL"]
    else:
        collection, id_field = COLLECTIONS[artifact.key]
        actual_ids = [getattr(item, id_field) for item in getattr(envelope.final_artifact, collection)]
    if len(actual_ids) != len(set(actual_ids)):
        raise ValueError("Final artifact instance IDs must be unique")
    if decision.artifact_ids != actual_ids:
        raise ValueError(f"multiplicity artifact_ids must exactly match the artifact instances: {actual_ids}")
    if decision.artifact_count != len(actual_ids):
        raise ValueError("multiplicity artifact_count does not match the artifact schema collection")
    expected = "SINGLE" if len(actual_ids) == 1 else "MULTIPLE"
    if decision.decision != expected:
        raise ValueError(f"multiplicity decision must be {expected} for {len(actual_ids)} artifact instances")


def run_finalization_stage(
    artifacts: list[ArtifactDefinition], control: ControlWorkbook, client, settings: dict[str, str],
    principle_contexts: dict[str, dict[str, Any]],
) -> None:
    print("\nFinal artifact design stage")
    for artifact in artifacts:
        name = artifact_folder_name(artifact.key)
        aggregate_path = ARTIFACT_ROOT / name / "_aggregate.json"
        final_path = FINAL_ARTIFACT_ROOT / f"{name}.json"
        csv_path = FINAL_CSV_ROOT / f"{name}.csv"
        try:
            if control.aggregate_get(artifact.key, "STATUS") not in {"SUCCESS", "MODIFIED"} or not aggregate_path.exists():
                control.final_stage(artifact.key, "PENDING", "A complete aggregate is not available")
                print(f"  {artifact.key}: PENDING (aggregate incomplete)")
                continue
            aggregate_envelope = json.loads(aggregate_path.read_text(encoding="utf-8"))
            aggregate = aggregate_envelope["optimized_artifact"]
            aggregate_hash = _hash_bytes(aggregate_path)
            principles = principle_contexts[artifact.key]
            input_hash = hashlib.sha256(
                f"{aggregate_hash}|{principles['corpus_sha256']}".encode("utf-8")
            ).hexdigest()
            envelope_model = final_envelope_model(artifact.key)

            existing_current = False
            if final_path.exists():
                recorded_mtime = control.aggregate_get(artifact.key, "FINAL_JSON_MTIME_NS")
                modified = recorded_mtime is not None and str(recorded_mtime) != mtime_ns(final_path)
                try:
                    existing = envelope_model.model_validate_json(final_path.read_text(encoding="utf-8"))
                    _validate_multiplicity(artifact, existing)
                    existing_current = modified or control.aggregate_get(artifact.key, "FINAL_INPUT_HASH") == input_hash
                    if modified:
                        control.final_stage(artifact.key, "MODIFIED")
                except Exception as error:
                    if modified:
                        control.final_stage(artifact.key, "MODIFIED", f"Human-edited final JSON needs correction: {error}")
                        print(f"  {artifact.key}: FAILED (invalid human-edited final JSON)")
                        continue
            if existing_current:
                nice_json_to_csv(final_path, csv_path)
                control.aggregate_set(artifact.key, "FINAL_CSV_PATH", str(csv_path.relative_to(ROOT)), save=False)
                control.aggregate_set(artifact.key, "FINAL_JSON_HASH", _hash_bytes(final_path), save=False)
                control.aggregate_set(artifact.key, "FINAL_JSON_MTIME_NS", mtime_ns(final_path), save=False)
                control.save()
                print(f"  {artifact.key}: SKIPPED ({'human-modified' if modified else 'current'})")
                continue

            control.final_stage(artifact.key, "RUNNING")
            candidate, review, attempts = finalize_until_approved(
                client, settings, artifact, envelope_model, aggregate, aggregate_hash,
                principles["corpus_sha256"], principles["text"], principles["chunk_ids"],
                lambda value: _validate_multiplicity(artifact, value),
            )
            value = candidate.model_dump(mode="json")
            value["review"] = review.model_dump(mode="json")
            value["review_attempts"] = attempts
            # Review metadata is kept in the workbook; the output itself remains the strict envelope schema.
            value.pop("review")
            value.pop("review_attempts")
            write_json_atomic(final_path, value)
            nice_json_to_csv(final_path, csv_path)
            control.aggregate_set(artifact.key, "FINAL_INPUT_HASH", input_hash, save=False)
            control.aggregate_set(artifact.key, "FINAL_JSON_PATH", str(final_path.relative_to(ROOT)), save=False)
            control.aggregate_set(artifact.key, "FINAL_JSON_HASH", _hash_bytes(final_path), save=False)
            control.aggregate_set(artifact.key, "FINAL_JSON_MTIME_NS", mtime_ns(final_path), save=False)
            control.aggregate_set(artifact.key, "FINAL_CSV_PATH", str(csv_path.relative_to(ROOT)), save=False)
            control.aggregate_set(artifact.key, "FINAL_REVIEW_ATTEMPTS", min(attempts, MAX_FINAL_RETRIES), save=False)
            control.aggregate_set(artifact.key, "FINAL_VALIDATOR_CORRECTION", "YES" if attempts > MAX_FINAL_RETRIES else "NO", save=False)
            control.final_stage(artifact.key, "SUCCESS")
            print(f"  {artifact.key}: SUCCESS (review attempts: {attempts})")
        except Exception as error:
            control.final_stage(artifact.key, "FAILED", f"{type(error).__name__}: {error}")
            print(f"  {artifact.key}: FAILED ({type(error).__name__}: {error})")
