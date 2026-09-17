from __future__ import annotations

from typing import Any


def cross_artifact_issues(artifact_key: str, value: dict[str, Any], dependencies: dict[str, dict[str, Any]]) -> list[str]:
    issues: list[str] = []
    dsd = dependencies.get("DSD_KEY_FAMILY", {})
    dataflow = dependencies.get("DATAFLOW", {})
    msd = dependencies.get("METADATA_STRUCTURE_DEFINITION_MSD", {})

    dsd_ids = {item.get("dsd_id") for item in dsd.get("data_structures", [])}
    dataflow_ids = {item.get("dataflow_id") for item in dataflow.get("dataflows", [])}
    msd_ids = {item.get("msd_id") for item in msd.get("metadata_structures", [])}

    if artifact_key == "DATAFLOW":
        for item in value.get("dataflows", []):
            if item.get("dsd_id") not in dsd_ids:
                issues.append(
                    f"Dataflow {item.get('dataflow_id')} references missing DSD {item.get('dsd_id')}; "
                    f"use one of {sorted(dsd_ids)}."
                )
    elif artifact_key == "METADATA_SET":
        for item in value.get("metadata_sets", []):
            if item.get("msd_id") not in msd_ids:
                issues.append(
                    f"Metadata set {item.get('metadata_set_id')} references missing MSD {item.get('msd_id')}; "
                    f"use one of {sorted(msd_ids)}."
                )
            if item.get("target_type") == "DATAFLOW" and item.get("target_id") not in dataflow_ids:
                issues.append(
                    f"Metadata set {item.get('metadata_set_id')} targets missing Dataflow {item.get('target_id')}; "
                    f"use the semantically corresponding ID from {sorted(dataflow_ids)}."
                )
    elif artifact_key == "AI_FILLABLE_DATA_TEMPLATE":
        for item in value.get("templates", []):
            if item.get("dsd_id") not in dsd_ids:
                issues.append(
                    f"Template {item.get('template_id')} references missing DSD {item.get('dsd_id')}; "
                    f"use one of {sorted(dsd_ids)}."
                )
    elif artifact_key == "CODEBOOK_AND_SOURCE_MAPPING":
        field_ids = {item.get("field_id") for item in value.get("fields", [])}
        metadata_concept_ids = {
            concept.get("concept_id")
            for structure in msd.get("metadata_structures", [])
            for concept in structure.get("concepts", [])
        }
        valid_targets = field_ids | metadata_concept_ids
        for item in value.get("source_value_mappings", []):
            if item.get("target_field") not in valid_targets:
                issues.append(
                    f"Source mapping target_field {item.get('target_field')} is neither a declared codebook field "
                    "nor an accepted MSD concept ID. Add a complete CodebookField entry with exactly this field_id "
                    "when it is a legitimate structural routing field; otherwise change the mapping to the exact "
                    "accepted field or MSD concept ID. Every TARGET_FIELD must be documented."
                )
    return issues
