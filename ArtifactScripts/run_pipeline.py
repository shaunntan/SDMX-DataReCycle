#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

from pipeline.agents import generate_until_semantically_valid, load_client
from pipeline.aggregation import run_aggregation_stage
from pipeline.artifacts import artifact_folder_name, discover_artifacts, file_hash
from pipeline.config import ARTIFACT_ROOT, EMBEDDING_MODEL, EMBEDDING_ROOT, INPUTS, MAX_SEMANTIC_RETRIES, PIPELINE_VERSION, SUPPORTED_EXTENSIONS, TEXT_ROOT, ensure_directories
from pipeline.control import ControlWorkbook
from pipeline.consistency import run_consistency_stage
from pipeline.cross_validation import cross_artifact_issues
from pipeline.dependency_graph import ARTIFACT_ORDER, dependency_material
from pipeline.converters import extract_text
from pipeline.csv_companion import csv_to_value, json_to_csv, mtime_ns, write_json_atomic
from pipeline.embeddings import build_embedder, embed_and_save, load_embeddings, retrieve, sha256_text
from pipeline.finalization import run_finalization_stage
from pipeline.models import model_for
from pipeline.principle_embeddings import build_principle_contexts
from pipeline.standards import authoritative_evidence
from pipeline.xml_ingest import run_xml_ingestion
from pipeline.xml_export import run_final_xml_export


def stable_stem(source: Path, sources: list[Path]) -> str:
    collisions = [item for item in sources if item.stem.casefold() == source.stem.casefold()]
    if len(collisions) == 1:
        return source.stem
    relative = source.relative_to(INPUTS).as_posix()
    return f"{source.stem}_{hashlib.sha256(relative.encode()).hexdigest()[:10]}"


def folder_name(key: str) -> str:
    return artifact_folder_name(key)


def sync_artifact_companion(control, row, artifact, output: Path, model) -> bool:
    """Synchronize JSON/CSV edits. Return True when a human modification was imported."""
    csv_path = output.with_suffix(".csv")
    control.set(row, f"{artifact.key}_JSON_PATH", str(output.relative_to(output.parents[2])), save=False)
    if not output.exists():
        control.save()
        return False
    recorded_json = control.get(row, f"{artifact.key}_JSON_MTIME_NS")
    recorded_csv = control.get(row, f"{artifact.key}_CSV_MTIME_NS")
    json_changed = recorded_json is not None and str(recorded_json) != mtime_ns(output)
    csv_changed = csv_path.exists() and recorded_csv is not None and str(recorded_csv) != mtime_ns(csv_path)
    modified = False
    control.stage(row, f"{artifact.key}_CSV", "RUNNING")
    try:
        if csv_changed and (not json_changed or csv_path.stat().st_mtime_ns >= output.stat().st_mtime_ns):
            validated = model.model_validate(csv_to_value(csv_path))
            write_json_atomic(output, validated.model_dump(mode="json"))
            json_to_csv(output, csv_path)
            modified = True
        else:
            model.model_validate_json(output.read_text(encoding="utf-8"))
            if json_changed or not csv_path.exists() or recorded_csv is None:
                json_to_csv(output, csv_path)
            modified = json_changed
        control.set(row, f"{artifact.key}_JSON_MTIME_NS", mtime_ns(output), save=False)
        control.set(row, f"{artifact.key}_CSV_MTIME_NS", mtime_ns(csv_path), save=False)
        control.stage(row, f"{artifact.key}_CSV", "SUCCESS")
        if modified:
            control.stage(row, artifact.key, "MODIFIED")
            control.set(row, f"{artifact.key}_AGGREGATED", "NO", save=False)
            control.set(row, f"{artifact.key}_AGGREGATED_JSON_HASH", "", save=False)
            control.save()
        return modified
    except Exception as error:
        control.stage(row, f"{artifact.key}_CSV", "FAILED", f"{type(error).__name__}: {error}")
        control.stage(row, artifact.key, "MODIFIED", f"Human-edited JSON/CSV needs correction: {type(error).__name__}: {error}")
        control.set(row, f"{artifact.key}_AGGREGATED", "NO", save=False)
        control.set(row, f"{artifact.key}_AGGREGATED_JSON_HASH", "", save=False)
        control.save()
        raise


def selected_sources(args) -> list[Path]:
    sources = sorted(path for path in INPUTS.rglob("*") if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS)
    if args.file:
        needle = args.file.casefold()
        sources = [path for path in sources if path.name.casefold() == needle or str(path.relative_to(INPUTS)).casefold() == needle]
    return sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Resumable report-to-SDMX artifact pipeline")
    parser.add_argument("--file", help="Process one input filename or relative path")
    parser.add_argument("--artifact", help="Process one discovered artifact key")
    parser.add_argument("--force", action="store_true", help="Invalidate and rerun selected stages")
    parser.add_argument("--refresh-standards", action="store_true", help="Refresh cached official-source excerpts")
    parser.add_argument("--skip-aggregate", action="store_true", help="Run per-report stages without aggregate optimization")
    parser.add_argument("--aggregate-only", action="store_true", help="Skip per-report work and update aggregates from existing artifacts")
    args = parser.parse_args()
    ensure_directories()
    artifacts, shared_references = discover_artifacts()
    rank = {key: index for index, key in enumerate(ARTIFACT_ORDER)}
    artifacts.sort(key=lambda item: rank.get(item.key, len(rank)))
    if args.artifact:
        requested = re.sub(r"[^A-Z0-9]+", "_", args.artifact.upper()).strip("_")
        artifacts = [item for item in artifacts if item.key == requested]
        if not artifacts:
            raise ValueError(f"Unknown artifact: {args.artifact}")
    control = ControlWorkbook(artifacts)
    sources = selected_sources(args)
    print(f"Discovered {len(artifacts)} artifacts and {len(sources)} supported input files.")
    if not sources:
        print("No supported files found in Inputs.")
        return 0
    official_evidence = authoritative_evidence(args.refresh_standards)
    shared_references = shared_references + "\n\n===== ONLINE OFFICIAL-SOURCE EVIDENCE =====\n" + official_evidence
    embedder = None
    client = settings = None
    rows_by_path = {}
    stems_by_path = {}
    for source in sources:
        relative = source.relative_to(INPUTS).as_posix()
        rows_by_path[relative], _ = control.sync_file(source, relative, file_hash(source))
        stems_by_path[relative] = stable_stem(source, sources)
    if args.aggregate_only:
        for source in sources:
            relative = source.relative_to(INPUTS).as_posix()
            row = rows_by_path[relative]
            stem = stable_stem(source, sources)
            for artifact in artifacts:
                output = ARTIFACT_ROOT / folder_name(artifact.key) / f"{stem}.json"
                if output.exists() and control.get(row, f"{artifact.key}_STATUS") in {"SUCCESS", "RUNNING", "MODIFIED"}:
                    try:
                        sync_artifact_companion(control, row, artifact, output, model_for(artifact.key))
                    except Exception:
                        print(f"  {artifact.key}: FAILED (human-edited JSON/CSV is invalid)")
    for source in ([] if args.aggregate_only else sources):
        relative = source.relative_to(INPUTS).as_posix()
        source_hash = file_hash(source)
        stem = stable_stem(source, sources)
        row = rows_by_path[relative]
        if args.force:
            for prefix in ("TXT", "EMBEDDING", *[item.key for item in artifacts]):
                control.stage(row, prefix, "PENDING")
            for artifact in artifacts:
                control.set(row, f"{artifact.key}_AGGREGATED", "NO", save=False)
            control.save()
        print(f"\n{relative}")
        text_path = TEXT_ROOT / f"{stem}.txt"
        text = ""
        txt_status = control.get(row, "TXT_STATUS")
        try:
            if txt_status == "SUCCESS" and text_path.exists() and control.get(row, "TXT_HASH") == sha256_text(text_path.read_text(encoding="utf-8")):
                text = text_path.read_text(encoding="utf-8")
                print("  TXT: SKIPPED (current)")
            else:
                control.stage(row, "TXT", "RUNNING")
                text = extract_text(source)
                if not re.sub(r"\[[^\]]+\]", "", text).strip():
                    raise ValueError("No machine-readable text was extracted")
                text_path.write_text(text, encoding="utf-8", newline="\n")
                control.set(row, "TXT_HASH", sha256_text(text), save=False)
                control.stage(row, "TXT", "SUCCESS")
                print(f"  TXT: SUCCESS -> {text_path.relative_to(TEXT_ROOT.parent)}")
        except Exception as error:
            control.stage(row, "TXT", "FAILED", f"{type(error).__name__}: {error}")
            print(f"  TXT: FAILED ({type(error).__name__}: {error})")
            continue
        txt_hash = sha256_text(text)
        embedding_dir = EMBEDDING_ROOT / stem
        vectors = chunks = manifest = None
        try:
            current = False
            if control.get(row, "EMBEDDING_STATUS") == "SUCCESS" and control.get(row, "EMBEDDING_TXT_HASH") == txt_hash:
                try:
                    vectors, chunks, manifest = load_embeddings(embedding_dir)
                    current = manifest["txt_hash"] == txt_hash and manifest["embedding_model"] == EMBEDDING_MODEL
                except Exception:
                    current = False
            if current:
                print("  EMBEDDINGS: SKIPPED (current)")
            else:
                control.stage(row, "EMBEDDING", "RUNNING")
                if embedder is None:
                    print(f"  Loading local embedding model: {EMBEDDING_MODEL}")
                    embedder = build_embedder()
                vectors, chunks = embed_and_save(text, source.name, source_hash, embedding_dir, embedder)
                manifest = json.loads((embedding_dir / "manifest.json").read_text(encoding="utf-8"))
                control.set(row, "EMBEDDING_TXT_HASH", txt_hash, save=False)
                control.stage(row, "EMBEDDING", "SUCCESS")
                print(f"  EMBEDDINGS: SUCCESS ({len(chunks)} chunks, {vectors.shape[1]} dimensions)")
        except Exception as error:
            control.stage(row, "EMBEDDING", "FAILED", f"{type(error).__name__}: {error}")
            print(f"  EMBEDDINGS: FAILED ({type(error).__name__}: {error})")
            continue
        if embedder is None:
            embedder = build_embedder()
        base_artifact_input = f"{source_hash}|{txt_hash}|{manifest['embedding_model']}|{PIPELINE_VERSION}"
        for artifact in artifacts:
            output = ARTIFACT_ROOT / folder_name(artifact.key) / f"{stem}.json"
            dependency_text, dependency_hashes, dependency_values = dependency_material(artifact.key, stem)
            dependency_suffix = f"|{dependency_hashes}" if dependency_hashes else ""
            artifact_input_hash = hashlib.sha256(f"{base_artifact_input}{dependency_suffix}".encode()).hexdigest()
            model = model_for(artifact.key)
            if control.get(row, f"{artifact.key}_STATUS") in {"SUCCESS", "RUNNING", "MODIFIED"} and output.exists():
                try:
                    sync_artifact_companion(control, row, artifact, output, model)
                except Exception:
                    print(f"  {artifact.key}: FAILED (human-edited JSON/CSV is invalid)")
                    continue
            valid_existing = False
            if output.exists():
                try:
                    model.model_validate_json(output.read_text(encoding="utf-8"))
                    valid_existing = True
                except Exception:
                    valid_existing = False
            status = control.get(row, f"{artifact.key}_STATUS")
            current = (
                valid_existing
                and status in {"SUCCESS", "RUNNING", "MODIFIED"}
                and control.get(row, f"{artifact.key}_PRINCIPLES_HASH") == artifact.sha256
                and control.get(row, f"{artifact.key}_INPUT_HASH") == artifact_input_hash
                and not cross_artifact_issues(artifact.key, model.model_validate_json(output.read_text(encoding="utf-8")).model_dump(mode="json"), dependency_values)
            )
            if current:
                if status == "RUNNING":
                    control.stage(row, artifact.key, "SUCCESS")
                print(f"  {artifact.key}: SKIPPED ({'human-modified' if status == 'MODIFIED' else 'current'})")
                continue
            try:
                control.stage(row, artifact.key, "RUNNING")
                query = f"{artifact.name}. Find report evidence needed to construct and validate this SDMX artifact, including tables, definitions, units, dimensions, statuses, methodology, sources, caveats, and classifications.\n{artifact.text[:3000]}"
                relevant = retrieve(embedder, vectors, chunks, query)
                context = "\n\n".join(f"<<<CHUNK:{item['chunk_id']} PAGE:{item.get('page')} TABLE:{item.get('table')}>>>\n{item['text']}" for item in relevant)
                if len(text) <= 24000:
                    context += "\n\n<<<COMPLETE_SHORT_REPORT>>>\n" + text
                if client is None:
                    client, settings = load_client()
                generation_references = shared_references + dependency_text
                generated, semantic_attempts = generate_until_semantically_valid(
                    client, settings, artifact, model, source.name, source_hash, context,
                    [item["chunk_id"] for item in relevant], generation_references,
                    lambda value, key=artifact.key, deps=dependency_values: cross_artifact_issues(key, value, deps),
                )
                validated = model.model_validate(generated.model_dump(mode="json"))
                write_json_atomic(output, validated.model_dump(mode="json"))
                control.set(row, f"{artifact.key}_PRINCIPLES_HASH", artifact.sha256, save=False)
                control.set(row, f"{artifact.key}_INPUT_HASH", artifact_input_hash, save=False)
                control.set(row, f"{artifact.key}_JSON_PATH", str(output.relative_to(ARTIFACT_ROOT.parent)), save=False)
                control.set(row, f"{artifact.key}_JSON_MTIME_NS", mtime_ns(output), save=False)
                json_to_csv(output, output.with_suffix(".csv"))
                control.set(row, f"{artifact.key}_CSV_MTIME_NS", mtime_ns(output.with_suffix(".csv")), save=False)
                control.set(row, f"{artifact.key}_AGGREGATED", "NO", save=False)
                control.set(row, f"{artifact.key}_AGGREGATED_JSON_HASH", "", save=False)
                control.set(row, f"{artifact.key}_SEMANTIC_ATTEMPTS", min(semantic_attempts, MAX_SEMANTIC_RETRIES), save=False)
                control.set(row, f"{artifact.key}_VALIDATOR_CORRECTION", "YES" if semantic_attempts > MAX_SEMANTIC_RETRIES else "NO", save=False)
                control.stage(row, f"{artifact.key}_CSV", "SUCCESS")
                control.stage(row, artifact.key, "SUCCESS")
                print(f"  {artifact.key}: SUCCESS (semantic attempts: {semantic_attempts})")
            except Exception as error:
                control.stage(row, artifact.key, "FAILED", f"{type(error).__name__}: {error}")
                print(f"  {artifact.key}: FAILED ({type(error).__name__}: {error})")
    xml_approved = run_xml_ingestion(artifacts, control)
    if embedder is None:
        print(f"\nLoading local embedding model for consistency checks: {EMBEDDING_MODEL}")
        embedder = build_embedder()
    if client is None:
        client, settings = load_client()
    consistency_approved = run_consistency_stage(
        artifacts, sources, stems_by_path, control, embedder, client, settings, shared_references,
    )
    if not args.skip_aggregate and consistency_approved and xml_approved:
        principle_contexts = build_principle_contexts(embedder, artifacts)
        run_aggregation_stage(artifacts, control, client, settings, principle_contexts)
        run_finalization_stage(artifacts, control, client, settings, principle_contexts)
        run_final_xml_export(artifacts, control)
    elif not args.skip_aggregate:
        print("\nAggregation skipped because report/XML conversion and consistency are not fully approved.")
    print("\nPipeline run complete.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted; current workbook states are preserved.", file=sys.stderr)
        raise SystemExit(130)
