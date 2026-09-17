from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .agents import generate_until_semantically_valid
from .artifacts import ArtifactDefinition, artifact_folder_name
from .config import ARTIFACT_ROOT, EMBEDDING_ROOT, INPUTS, MAX_SEMANTIC_RETRIES, PIPELINE_VERSION, TEXT_ROOT
from .control import ControlWorkbook
from .cross_validation import cross_artifact_issues
from .csv_companion import json_to_csv, mtime_ns, write_json_atomic
from .dependency_graph import ARTIFACT_ORDER, AUTHORITY_HIERARCHY, dependency_material
from .embeddings import load_embeddings, retrieve, sha256_text
from .models import model_for


MAX_CONSISTENCY_PASSES = 2


def _artifact_input_hash(source_hash: str, text_hash: str, embedding_model: str, dependency_hashes: str) -> str:
    suffix = f"|{dependency_hashes}" if dependency_hashes else ""
    base = f"{source_hash}|{text_hash}|{embedding_model}|{PIPELINE_VERSION}"
    return hashlib.sha256(f"{base}{suffix}".encode()).hexdigest()


def _sync_accepted(
    artifacts: list[ArtifactDefinition], control: ControlWorkbook, row: int, stem: str,
    source_hash: str, text_hash: str, embedding_model: str,
) -> None:
    for artifact in artifacts:
        output = ARTIFACT_ROOT / artifact_folder_name(artifact.key) / f"{stem}.json"
        if not output.exists():
            continue
        _, dependency_hashes, dependencies = dependency_material(artifact.key, stem)
        value = model_for(artifact.key).model_validate_json(output.read_text(encoding="utf-8")).model_dump(mode="json")
        issues = cross_artifact_issues(artifact.key, value, dependencies)
        if issues:
            raise ValueError(f"{artifact.key}: {'; '.join(issues)}")
        csv_path = output.with_suffix(".csv")
        json_to_csv(output, csv_path)
        control.set(row, f"{artifact.key}_INPUT_HASH", _artifact_input_hash(source_hash, text_hash, embedding_model, dependency_hashes), save=False)
        control.set(row, f"{artifact.key}_JSON_MTIME_NS", mtime_ns(output), save=False)
        control.set(row, f"{artifact.key}_CSV_MTIME_NS", mtime_ns(csv_path), save=False)
        control.set(row, f"{artifact.key}_CSV_STATUS", "SUCCESS", save=False)


def run_consistency_stage(
    artifacts: list[ArtifactDefinition], sources: list[Path], stems: dict[str, str],
    control: ControlWorkbook, embedder, client, settings: dict[str, str], shared_references: str,
) -> bool:
    print("\nCross-artifact consistency gate")
    rank = {key: index for index, key in enumerate(ARTIFACT_ORDER)}
    ordered = sorted(artifacts, key=lambda item: rank.get(item.key, len(rank)))
    all_approved = True
    for source in sources:
        relative = source.relative_to(INPUTS).as_posix()
        row = control.find_row(relative)
        stem = stems[relative]
        missing = [
            artifact.key for artifact in ordered
            if not (ARTIFACT_ROOT / artifact_folder_name(artifact.key) / f"{stem}.json").exists()
        ]
        if missing:
            control.stage(row, "CONSISTENCY", "PENDING", "Missing artifacts: " + ", ".join(missing))
            print(f"  {relative}: PENDING ({len(missing)} artifacts missing)")
            all_approved = False
            continue
        try:
            text = (TEXT_ROOT / f"{stem}.txt").read_text(encoding="utf-8")
            vectors, chunks, manifest = load_embeddings(EMBEDDING_ROOT / stem)
            source_hash = str(control.get(row, "FILE_HASH"))
            text_hash = sha256_text(text)
            approved = False
            for pass_number in range(1, MAX_CONSISTENCY_PASSES + 1):
                repairs = 0
                for artifact in ordered:
                    output = ARTIFACT_ROOT / artifact_folder_name(artifact.key) / f"{stem}.json"
                    model = model_for(artifact.key)
                    value = model.model_validate_json(output.read_text(encoding="utf-8")).model_dump(mode="json")
                    dependency_text, _, dependencies = dependency_material(artifact.key, stem)
                    issues = cross_artifact_issues(artifact.key, value, dependencies)
                    if not issues:
                        continue
                    repairs += 1
                    control.stage(row, "CONSISTENCY", "RUNNING", f"Repairing {artifact.key}: {'; '.join(issues)}")
                    query = f"{artifact.name}. Evidence needed to repair these cross-artifact inconsistencies: {'; '.join(issues)}"
                    relevant = retrieve(embedder, vectors, chunks, query)
                    context = "\n\n".join(
                        f"<<<CHUNK:{item['chunk_id']} PAGE:{item.get('page')} TABLE:{item.get('table')}>>>\n{item['text']}"
                        for item in relevant
                    )
                    if len(text) <= 24000:
                        context += "\n\n<<<COMPLETE_SHORT_REPORT>>>\n" + text
                    repair_context = (
                        shared_references + dependency_text
                        + "\n\n===== MANDATORY CONSISTENCY REPAIR =====\n"
                        + "\n".join(issues) + "\n\n" + AUTHORITY_HIERARCHY
                        + "\n\nREJECTED ARTIFACT JSON:\n" + json.dumps(value, ensure_ascii=False)
                    )
                    generated, attempts = generate_until_semantically_valid(
                        client, settings, artifact, model, source.name, source_hash, context,
                        [item["chunk_id"] for item in relevant], repair_context,
                        lambda candidate, key=artifact.key, deps=dependencies: cross_artifact_issues(key, candidate, deps),
                    )
                    write_json_atomic(output, generated.model_dump(mode="json"))
                    json_to_csv(output, output.with_suffix(".csv"))
                    control.set(row, f"{artifact.key}_VALIDATOR_CORRECTION", "YES" if attempts > MAX_SEMANTIC_RETRIES else "NO", save=False)
                    control.set(row, f"{artifact.key}_AGGREGATED", "NO", save=False)
                    control.stage(row, artifact.key, "SUCCESS")
                remaining = []
                for check_artifact in ordered:
                    check_output = ARTIFACT_ROOT / artifact_folder_name(check_artifact.key) / f"{stem}.json"
                    check_value = model_for(check_artifact.key).model_validate_json(
                        check_output.read_text(encoding="utf-8")
                    ).model_dump(mode="json")
                    _, _, check_dependencies = dependency_material(check_artifact.key, stem)
                    remaining.extend(
                        f"{check_artifact.key}: {issue}"
                        for issue in cross_artifact_issues(check_artifact.key, check_value, check_dependencies)
                    )
                if not remaining:
                    approved = True
                    control.set(row, "CONSISTENCY_PASSES", pass_number, save=False)
                    break
            if not approved:
                raise ValueError(f"Consistency was not achieved after {MAX_CONSISTENCY_PASSES} passes")
            _sync_accepted(ordered, control, row, stem, source_hash, text_hash, manifest["embedding_model"])
            control.stage(row, "CONSISTENCY", "SUCCESS")
            print(f"  {relative}: SUCCESS")
        except Exception as error:
            control.stage(row, "CONSISTENCY", "FAILED", f"{type(error).__name__}: {error}")
            print(f"  {relative}: FAILED ({type(error).__name__}: {error})")
            all_approved = False
    return all_approved
