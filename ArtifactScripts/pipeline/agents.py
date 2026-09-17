from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path
from typing import Any, Callable

from openai import OpenAI
from pydantic import BaseModel, ValidationError

from .artifacts import ArtifactDefinition
from .config import KEYS_FILE, MAX_AGGREGATE_RETRIES, MAX_API_ATTEMPTS, MAX_FINAL_RETRIES, MAX_SCHEMA_RETRIES, MAX_SEMANTIC_RETRIES
from .models import AggregateReview, FinalReview, SemanticReview


def load_client() -> tuple[OpenAI, dict[str, str]]:
    data = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
    required = ("api-key", "endUserId", "azure-endpoint", "azure-deployment")
    missing = [key for key in required if not isinstance(data.get(key), str) or not data[key].strip()]
    if missing:
        raise ValueError("Missing Azure configuration fields: " + ", ".join(missing))
    client = OpenAI(api_key="unused", base_url=f"{data['azure-endpoint'].rstrip('/')}/openai/v1/", default_headers={"api-key": data["api-key"]}, timeout=1800, max_retries=0)
    return client, data


def _strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    schema = model.model_json_schema()
    def visit(value: Any) -> None:
        if isinstance(value, dict):
            if value.get("type") == "object" and "properties" in value:
                value["additionalProperties"] = False
            for nested in value.values():
                visit(nested)
        elif isinstance(value, list):
            for nested in value:
                visit(nested)
    visit(schema)
    return schema


def call_structured(client: OpenAI, settings: dict[str, str], prompt: str, model: type[BaseModel], schema_name: str) -> dict[str, Any]:
    last_error: Exception | None = None
    for attempt in range(1, MAX_API_ATTEMPTS + 1):
        try:
            response = client.responses.create(
                model=settings["azure-deployment"], safety_identifier=settings["endUserId"], input=prompt,
                text={"format": {"type": "json_schema", "name": schema_name[:64], "strict": True, "schema": _strict_schema(model)}},
            )
            if not response.output_text:
                raise ValueError("Azure returned empty structured output")
            value = json.loads(response.output_text)
            if not isinstance(value, dict):
                raise ValueError("Azure output was not a JSON object")
            return value
        except Exception as error:
            last_error = error
            if attempt == MAX_API_ATTEMPTS:
                break
            wait = attempt * 5
            print(f"      Azure attempt {attempt}/{MAX_API_ATTEMPTS} failed ({type(error).__name__}); retrying in {wait}s", file=sys.stderr, flush=True)
            time.sleep(wait)
    raise RuntimeError(f"Azure request failed after {MAX_API_ATTEMPTS} attempts: {type(last_error).__name__}") from last_error


def generate_and_validate(
    client: OpenAI, settings: dict[str, str], artifact: ArtifactDefinition, model: type[BaseModel],
    source_name: str, source_hash: str, context: str, chunk_ids: list[int], shared_references: str,
    previous: dict[str, Any] | None = None, semantic_feedback: SemanticReview | None = None,
) -> BaseModel:
    errors = ""
    for schema_attempt in range(1, MAX_SCHEMA_RETRIES + 1):
        repair = ""
        if previous and semantic_feedback:
            repair = f"\nPREVIOUS JSON:\n{json.dumps(previous, ensure_ascii=False)}\nSEMANTIC ISSUES:\n{semantic_feedback.model_dump_json()}\nRepair every issue while staying faithful to evidence."
        if errors:
            repair += f"\nTHE PREVIOUS RESPONSE FAILED PYDANTIC VALIDATION. Correct these exact errors:\n{errors}"
        prompt = f"""You are the dedicated SDMX artifact generator for {artifact.name}. Return only the requested structured JSON.
Use the report as evidence, not as the structure. Do not invent facts. Preserve multiple statistical structures when justified, but do not equate one table with one DSD. Reuse authoritative SDMX concepts and codes before proposing local ones. Any ACCEPTED RELATED or AUTHORITATIVE ARTIFACT in the supplied context is binding: reuse its IDs exactly and never create an alias for an existing DSD, Dataflow, MSD, concept, codelist, or field. Every Codebook source mapping TARGET_FIELD must be documented by a complete CodebookField entry or be the exact ID of an accepted MSD concept. A reference in the principles is not proof that a code fits: use CONFIRMED only when supplied external evidence confirms it; otherwise use CANDIDATE or UNVERIFIED. Every field specifically named evidence_quote must be copied verbatim from the supplied report context. The `standard_references[].evidence` field instead summarizes evidence from the named external source and must never be presented as a report quote. The top-level `source_report` is a pipeline provenance identifier supplied above and is not an evidence quote; copy the supplied filename exactly. Use non-empty explicit values such as 'not stated' where the schema requires text and the report is silent, and record genuine gaps in limitations. When an exact standard concept ID/version cannot be confirmed from supplied external evidence, mark it CANDIDATE or UNVERIFIED and explicitly preserve that gap rather than inventing a confirmation.

SOURCE REPORT: {source_name}
SOURCE SHA256: {source_hash}
PRINCIPLES FILE: {artifact.path.name}
PRINCIPLES SHA256: {artifact.sha256}
RETRIEVED CHUNK IDS: {chunk_ids}

ARTIFACT PRINCIPLES:
{artifact.text}

SHARED REFERENCE CATALOGS:
{shared_references}

RETRIEVED REPORT EVIDENCE:
{context}
{repair}
"""
        value = call_structured(client, settings, prompt, model, f"generate_{artifact.key.lower()}")
        try:
            return model.model_validate(value)
        except ValidationError as error:
            errors = str(error)
    raise ValueError(f"Pydantic validation failed after {MAX_SCHEMA_RETRIES} attempts: {errors}")


def semantic_review(
    client: OpenAI, settings: dict[str, str], artifact: ArtifactDefinition,
    generated: BaseModel, context: str, shared_references: str,
) -> SemanticReview:
    prompt = f"""You are an independent senior SDMX semantic validator. Do not defer to the generator. Judge whether the JSON faithfully represents the supplied report and follows the artifact principles. Check dimensions versus attributes, TIME_PERIOD, OBS_VALUE, units, status flags, multiple structures, methodology placement, caveats, standard-code semantics and versions, unsupported claims, omissions, and justification of local concepts/codes. Fields specifically named `evidence_quote` must occur verbatim in REPORT CONTEXT. In contrast, `standard_references[].evidence` is external-source evidence and should be checked against SHARED REFERENCE CATALOGS, not against the report. The top-level `source_report` is a pipeline provenance filename supplied to the generator and is not required to occur inside report content. Do not require an exact standard mapping when the supplied official evidence cannot confirm one; in that case CANDIDATE or UNVERIFIED plus a clear limitation is correct and safer than invention. Return valid=true only when no repair is needed.

ARTIFACT PRINCIPLES:
{artifact.text}

SHARED REFERENCE CATALOGS:
{shared_references}

REPORT CONTEXT:
{context}

GENERATED JSON:
{generated.model_dump_json(indent=2)}
"""
    value = call_structured(client, settings, prompt, SemanticReview, f"review_{artifact.key.lower()}")
    return SemanticReview.model_validate(value)


def recover_verbatim_quotes(generated: BaseModel, context: str) -> BaseModel:
    """Replace whitespace-normalized model quotes with exact contiguous source text."""
    value = generated.model_dump(mode="json")

    def visit(item: Any) -> None:
        if isinstance(item, dict):
            quote = item.get("evidence_quote")
            if isinstance(quote, str) and quote.strip() and quote not in context:
                words = re.split(r"\s+", quote.strip())
                pattern = r"\s+".join(re.escape(word) for word in words if word)
                match = re.search(pattern, context)
                if match:
                    item["evidence_quote"] = match.group(0)
            for nested in item.values():
                visit(nested)
        elif isinstance(item, list):
            for nested in item:
                visit(nested)

    visit(value)
    return type(generated).model_validate(value)


def generate_until_semantically_valid(
    client: OpenAI, settings: dict[str, str], artifact: ArtifactDefinition, model: type[BaseModel],
    source_name: str, source_hash: str, context: str, chunk_ids: list[int], shared_references: str,
    local_validator: Callable[[dict[str, Any]], list[str]] | None = None,
) -> tuple[BaseModel, int]:
    previous = None
    feedback = None
    for semantic_attempt in range(1, MAX_SEMANTIC_RETRIES + 1):
        generated = generate_and_validate(client, settings, artifact, model, source_name, source_hash, context, chunk_ids, shared_references, previous, feedback)
        generated = recover_verbatim_quotes(generated, context)
        local_issues = local_validator(generated.model_dump(mode="json")) if local_validator else []
        if local_issues:
            review = SemanticReview(valid=False, issues=local_issues, repair_instructions=local_issues)
        else:
            review = semantic_review(client, settings, artifact, generated, context, shared_references)
        if review.valid:
            return generated, semantic_attempt
        previous = generated.model_dump(mode="json")
        feedback = review
        print(f"      Semantic review requested repair {semantic_attempt}/{MAX_SEMANTIC_RETRIES}: {'; '.join(review.issues)}", flush=True)
    repaired = validator_direct_repair(
        client, settings, artifact, model, previous or {}, feedback,
        context, shared_references,
        provenance={
            "source_report": source_name, "source_sha256": source_hash,
            "principles_file": artifact.path.name, "principles_sha256": artifact.sha256,
            "retrieved_chunk_ids": chunk_ids,
        },
    )
    repaired = recover_verbatim_quotes(repaired, context)
    remaining = local_validator(repaired.model_dump(mode="json")) if local_validator else []
    if remaining:
        raise ValueError("Validator correction left invalid cross-artifact references: " + "; ".join(remaining))
    return repaired, MAX_SEMANTIC_RETRIES + 1


def validator_direct_repair(
    client: OpenAI, settings: dict[str, str], artifact: ArtifactDefinition, model: type[BaseModel],
    candidate: dict[str, Any], feedback: SemanticReview | AggregateReview | FinalReview | None,
    evidence: str, best_practices: str, provenance: dict[str, Any] | None = None,
) -> BaseModel:
    errors = ""
    for _ in range(MAX_SCHEMA_RETRIES):
        prompt = f"""You are the independent validator and now have final correction authority after the configured review rounds were rejected.
Directly return a corrected `{artifact.name}` JSON. Apply every review instruction, retain every supported requirement, and follow the strict response schema. Do not merely describe changes.

REJECTED CANDIDATE:
{json.dumps(candidate, ensure_ascii=False)}

LAST REVIEW:
{feedback.model_dump_json(indent=2) if feedback else 'No structured review was available.'}

EVIDENCE OR REQUIRED INPUTS:
{evidence}

BEST-PRACTICE CONTEXT:
{best_practices}

REQUIRED PROVENANCE VALUES:
{json.dumps(provenance, ensure_ascii=False)}

PYDANTIC ERRORS FROM A PRIOR CORRECTION:
{errors}
"""
        value = call_structured(client, settings, prompt, model, f"validator_repair_{artifact.key.lower()}")
        if provenance:
            value.update(provenance)
        try:
            return model.model_validate(value)
        except ValidationError as error:
            errors = str(error)
    raise ValueError(f"Validator correction failed schema validation after {MAX_SCHEMA_RETRIES} attempts: {errors}")


def optimize_aggregate_candidate(
    client: OpenAI,
    settings: dict[str, str],
    artifact: ArtifactDefinition,
    model: type[BaseModel],
    aggregate_source_hash: str,
    previous_aggregate: dict[str, Any] | None,
    incremental_inputs: list[dict[str, Any]],
    expected_sources: list[str],
    best_practices: str,
    principle_chunk_ids: list[int],
    feedback: AggregateReview | None = None,
) -> BaseModel:
    validation_errors = ""
    for _ in range(MAX_SCHEMA_RETRIES):
        repair = ""
        if feedback is not None:
            repair += f"\nINSPECTOR FEEDBACK FROM THE REJECTED CANDIDATE:\n{feedback.model_dump_json(indent=2)}\nAddress every issue."
        if validation_errors:
            repair += f"\nPYDANTIC ERRORS FROM THE REJECTED CANDIDATE:\n{validation_errors}\nCorrect every error."
        prompt = f"""You are the consolidation agent for the SDMX artifact `{artifact.name}`.
Create the most efficient artifact possible while preserving every distinct statistical need represented by the accepted previous aggregate and the new or changed report artifacts. Remove duplicate concepts, codes, structures, fields, and metadata definitions only when their meanings are genuinely equivalent. Combine compatible structures, but never merge items whose statistical meanings, units, populations, classifications, attachment levels, or versions differ. Reuse shared components across reports. Preserve report-specific distinctions through dimensions, codes, mappings, or multiple structures when necessary.

Your response must follow exactly the same Pydantic schema as an individual `{artifact.name}` artifact. Set source_report to `AGGREGATE::{artifact.key}`, source_sha256 to `{aggregate_source_hash}`, principles_file to `{artifact.path.name}`, principles_sha256 to `{artifact.sha256}`, and retrieved_chunk_ids to `{principle_chunk_ids}`. The aggregate is a reusable cross-report design, not a report layout. Do not discard a requirement merely to reduce size.

SOURCE REPORTS THAT MUST BE COVERED:
{json.dumps(expected_sources, ensure_ascii=False)}

ARTIFACT PRINCIPLES:
{artifact.text}

RETRIEVED BEST PRACTICES FROM ALL ARTIFACT PRINCIPLE FILES:
{best_practices}

PREVIOUS APPROVED AGGREGATE (null means initial build):
{json.dumps(previous_aggregate, ensure_ascii=False)}

NEW OR CHANGED PER-REPORT ARTIFACTS:
{json.dumps(incremental_inputs, ensure_ascii=False)}
{repair}
"""
        value = call_structured(client, settings, prompt, model, f"aggregate_{artifact.key.lower()}")
        try:
            candidate = model.model_validate(value)
            candidate_value = candidate.model_dump(mode="json")
            candidate_value.update({
                "source_report": f"AGGREGATE::{artifact.key}",
                "source_sha256": aggregate_source_hash,
                "principles_file": artifact.path.name,
                "principles_sha256": artifact.sha256,
                "retrieved_chunk_ids": principle_chunk_ids,
            })
            return model.model_validate(candidate_value)
        except ValidationError as error:
            validation_errors = str(error)
    raise ValueError(f"Aggregate Pydantic validation failed after {MAX_SCHEMA_RETRIES} attempts: {validation_errors}")


def inspect_aggregate_candidate(
    client: OpenAI,
    settings: dict[str, str],
    artifact: ArtifactDefinition,
    previous_aggregate: dict[str, Any] | None,
    incremental_inputs: list[dict[str, Any]],
    candidate: BaseModel,
    expected_sources: list[str],
    best_practices: str,
) -> AggregateReview:
    prompt = f"""You are the independent coverage inspector for an optimized `{artifact.name}` aggregate.
Compare the proposed aggregate against BOTH the previous approved aggregate and every new or changed per-report artifact. Approve only if the candidate follows the artifact principles and covers at least every statistical need, distinction, code meaning, structure, metadata requirement, caveat, mapping, and source-specific variation represented by those inputs. Check that efficiency came from genuine reuse and deduplication, not omission. Check the same strict Pydantic shape conceptually, detect incompatible merges, and identify any redundancies that can still be safely removed.

The `covered_source_reports` list must include every source below when valid:
{json.dumps(expected_sources, ensure_ascii=False)}

ARTIFACT PRINCIPLES:
{artifact.text}

RETRIEVED BEST PRACTICES FROM ALL ARTIFACT PRINCIPLE FILES:
{best_practices}

PREVIOUS APPROVED AGGREGATE:
{json.dumps(previous_aggregate, ensure_ascii=False)}

NEW OR CHANGED PER-REPORT ARTIFACTS:
{json.dumps(incremental_inputs, ensure_ascii=False)}

PROPOSED OPTIMIZED AGGREGATE:
{candidate.model_dump_json(indent=2)}
"""
    value = call_structured(client, settings, prompt, AggregateReview, f"inspect_{artifact.key.lower()}")
    review = AggregateReview.model_validate(value)
    missing = sorted(set(expected_sources) - set(review.covered_source_reports))
    if review.valid and missing:
        return AggregateReview(
            valid=False,
            covered_source_reports=review.covered_source_reports,
            missing_source_reports=missing,
            missing_requirements=[],
            redundancies_remaining=[],
            schema_issues=[],
            repair_instructions=["Explicitly preserve and verify coverage for every missing source report."],
        )
    return review


def optimize_until_approved(
    client: OpenAI,
    settings: dict[str, str],
    artifact: ArtifactDefinition,
    model: type[BaseModel],
    aggregate_source_hash: str,
    previous_aggregate: dict[str, Any] | None,
    incremental_inputs: list[dict[str, Any]],
    expected_sources: list[str],
    best_practices: str,
    principle_chunk_ids: list[int],
) -> tuple[BaseModel, AggregateReview, int]:
    feedback = None
    for attempt in range(1, MAX_AGGREGATE_RETRIES + 1):
        candidate = optimize_aggregate_candidate(
            client, settings, artifact, model, aggregate_source_hash,
            previous_aggregate, incremental_inputs, expected_sources,
            best_practices, principle_chunk_ids, feedback,
        )
        review = inspect_aggregate_candidate(
            client, settings, artifact, previous_aggregate,
            incremental_inputs, candidate, expected_sources, best_practices,
        )
        if review.valid:
            return candidate, review, attempt
        feedback = review
        print(
            f"    Aggregate inspector requested repair {attempt}/{MAX_AGGREGATE_RETRIES}: "
            + "; ".join([*review.missing_source_reports, *review.missing_requirements, *review.redundancies_remaining, *review.schema_issues]),
            flush=True,
        )
    repaired = validator_direct_repair(
        client, settings, artifact, model,
        candidate.model_dump(mode="json"), feedback,
        json.dumps({"previous_aggregate": previous_aggregate, "new_inputs": incremental_inputs}, ensure_ascii=False),
        best_practices,
        provenance={
            "source_report": f"AGGREGATE::{artifact.key}", "source_sha256": aggregate_source_hash,
            "principles_file": artifact.path.name, "principles_sha256": artifact.sha256,
            "retrieved_chunk_ids": principle_chunk_ids,
        },
    )
    accepted = AggregateReview(
        valid=True, covered_source_reports=expected_sources, missing_source_reports=[],
        missing_requirements=[], redundancies_remaining=[], schema_issues=[], repair_instructions=[],
    )
    return repaired, accepted, MAX_AGGREGATE_RETRIES + 1


def finalize_candidate(
    client: OpenAI, settings: dict[str, str], artifact: ArtifactDefinition, envelope_model: type[BaseModel],
    aggregate: dict[str, Any], aggregate_hash: str, principles_hash: str,
    best_practices: str, chunk_ids: list[int], feedback: FinalReview | None = None,
) -> BaseModel:
    errors = ""
    for _ in range(MAX_SCHEMA_RETRIES):
        prompt = f"""You are the final SDMX artifact architect for `{artifact.name}`.
Decide whether the aggregate requirement is best represented by one artifact or multiple artifacts. Prefer one reusable artifact only when meanings and structures are compatible. If multiple are necessary, retain all of them in the artifact schema's collection and list every resulting artifact ID in multiplicity_decision. Return the strict final-envelope schema. Preserve every need in the aggregate and follow the retrieved best practices.

ARTIFACT KEY: {artifact.key}
AGGREGATE SHA256: {aggregate_hash}
PRINCIPLES CORPUS SHA256: {principles_hash}
BEST-PRACTICE CHUNK IDS: {chunk_ids}

AGGREGATE ARTIFACT:
{json.dumps(aggregate, ensure_ascii=False)}

RETRIEVED BEST PRACTICES:
{best_practices}

SECOND-AGENT FEEDBACK:
{feedback.model_dump_json(indent=2) if feedback else 'None'}

PYDANTIC ERRORS:
{errors}
"""
        value = call_structured(client, settings, prompt, envelope_model, f"finalize_{artifact.key.lower()}")
        value.update({
            "artifact_key": artifact.key, "artifact_name": artifact.name,
            "source_aggregate_sha256": aggregate_hash, "principles_sha256": principles_hash,
            "best_practice_chunk_ids": chunk_ids,
        })
        try:
            return envelope_model.model_validate(value)
        except ValidationError as error:
            errors = str(error)
    raise ValueError(f"Final artifact schema validation failed after {MAX_SCHEMA_RETRIES} attempts: {errors}")


def review_final_candidate(
    client: OpenAI, settings: dict[str, str], artifact: ArtifactDefinition,
    aggregate: dict[str, Any], candidate: BaseModel, best_practices: str,
) -> FinalReview:
    prompt = f"""You are the independent final-artifact inspector. Compare the proposed final envelope with every requirement in the aggregate. Verify that no requirement is omitted, the SINGLE/MULTIPLE choice is justified, artifact_count and artifact_ids correspond to the actual top-level artifact instances, and the result follows the supplied best practices. Approve only when every check passes.

AGGREGATE:
{json.dumps(aggregate, ensure_ascii=False)}

BEST PRACTICES:
{best_practices}

PROPOSED FINAL ENVELOPE:
{candidate.model_dump_json(indent=2)}
"""
    return FinalReview.model_validate(call_structured(client, settings, prompt, FinalReview, f"review_final_{artifact.key.lower()}"))


def finalize_until_approved(
    client: OpenAI, settings: dict[str, str], artifact: ArtifactDefinition, envelope_model: type[BaseModel],
    aggregate: dict[str, Any], aggregate_hash: str, principles_hash: str,
    best_practices: str, chunk_ids: list[int], local_validate,
) -> tuple[BaseModel, FinalReview, int]:
    feedback = None
    candidate = None
    for attempt in range(1, MAX_FINAL_RETRIES + 1):
        candidate = finalize_candidate(client, settings, artifact, envelope_model, aggregate, aggregate_hash, principles_hash, best_practices, chunk_ids, feedback)
        try:
            local_validate(candidate)
        except ValueError as error:
            feedback = FinalReview(
                valid=False, aggregate_requirements_covered=True, multiplicity_appropriate=False,
                best_practices_followed=True, missing_requirements=[], multiplicity_issues=[str(error)],
                best_practice_issues=[], schema_issues=[], repair_instructions=[str(error)],
            )
            print(f"    Final local validator requested repair {attempt}/{MAX_FINAL_RETRIES}: {error}", flush=True)
            continue
        review = review_final_candidate(client, settings, artifact, aggregate, candidate, best_practices)
        if review.valid:
            return candidate, review, attempt
        feedback = review
        print(f"    Final inspector requested repair {attempt}/{MAX_FINAL_RETRIES}: " + "; ".join(review.repair_instructions), flush=True)

    errors = ""
    for _ in range(MAX_SCHEMA_RETRIES):
        prompt = f"""You are the independent final-artifact inspector and now have correction authority after the configured review rounds were rejected. Directly return the fully corrected final envelope, not advice. Preserve every aggregate requirement and make the multiplicity declaration match the actual artifact instances.

AGGREGATE:
{json.dumps(aggregate, ensure_ascii=False)}
BEST PRACTICES:
{best_practices}
REJECTED FINAL ENVELOPE:
{candidate.model_dump_json(indent=2) if candidate else '{}'}
LAST REVIEW:
{feedback.model_dump_json(indent=2) if feedback else '{}'}
PYDANTIC OR LOCAL VALIDATION ERRORS:
{errors}
"""
        value = call_structured(client, settings, prompt, envelope_model, f"validator_final_{artifact.key.lower()}")
        value.update({
            "artifact_key": artifact.key, "artifact_name": artifact.name,
            "source_aggregate_sha256": aggregate_hash, "principles_sha256": principles_hash,
            "best_practice_chunk_ids": chunk_ids,
        })
        try:
            repaired = envelope_model.model_validate(value)
            local_validate(repaired)
            accepted = FinalReview(
                valid=True, aggregate_requirements_covered=True, multiplicity_appropriate=True,
                best_practices_followed=True, missing_requirements=[], multiplicity_issues=[],
                best_practice_issues=[], schema_issues=[], repair_instructions=[],
            )
            return repaired, accepted, MAX_FINAL_RETRIES + 1
        except (ValidationError, ValueError) as error:
            errors = str(error)
    raise ValueError(f"Final validator correction failed after {MAX_SCHEMA_RETRIES} schema attempts: {errors}")
