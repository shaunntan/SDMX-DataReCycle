#!/usr/bin/env python3
"""Codex-driven conversion of a report's extracted text into Parquet, shaped
by an accepted DSD's dimensions/attributes/measure.

For each DataStructure in a DSD/Key Family artifact, this asks Codex (in
workspace-write sandbox mode, since it needs to write and can try running a
script -- unlike the strict-JSON extraction calls in pipeline/agents.py) to
author convert.py against the pipeline's already-extracted report text
(Inputs_TXT/<stem>.txt), producing output.parquet with one column per DSD
component. No automatic retry loop: if the script doesn't produce a valid
parquet file, the failure and whatever Codex wrote are surfaced as-is.
"""
from __future__ import annotations

import decimal
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _json_default(value: Any) -> Any:
    if isinstance(value, decimal.Decimal):
        return float(value)
    return str(value)

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pipeline.config import CODEX_BIN, CODEX_CALL_TIMEOUT, TEXT_ROOT  # noqa: E402

DATA_CONVERSIONS_ROOT = Path(__file__).resolve().parents[1] / "Data Conversions"
PREVIEW_ROWS = 30


def build_prompt(dsd: dict[str, Any]) -> str:
    columns = []
    for component in dsd.get("components", []):
        columns.append(
            {
                "concept_id": component.get("concept_id"),
                "role": component.get("role"),
                "data_type": component.get("data_type"),
                "codelist_id": component.get("codelist_id"),
                "notes": component.get("notes"),
            }
        )
    return f"""You are a data engineer. A file "report_text.txt" in this directory contains the
extracted text of a statistical report. Your job: write a Python script named
"convert.py" that:

1. Reads report_text.txt.
2. Extracts the tabular observations relevant to this statistical structure
   (statistical_scope below) -- there may be other tables/structures in the
   text that belong to a DIFFERENT dataset; ignore those.
3. Builds a pandas DataFrame with EXACTLY one column per component below,
   named by its concept_id, holding the value for each observation row.
4. Writes the DataFrame to "output.parquet" in this directory using
   df.to_parquet("output.parquet", engine="pyarrow"), with no index column.
5. Run the script yourself to confirm output.parquet is actually produced
   before you finish. Use only pandas/pyarrow/stdlib (already installed).

DSD: {dsd.get("dsd_id")} -- {dsd.get("name")}
STATISTICAL SCOPE: {dsd.get("statistical_scope")}

COMPONENTS (id, role, data_type, codelist_id, notes):
{json.dumps(columns, indent=2)}

Do not invent observations that aren't in the report text. If a value is genuinely
missing for a column, use null/NaN rather than guessing.
"""


def run_codex(scratch_dir: Path) -> tuple[bool, str]:
    if not CODEX_BIN:
        return False, "No working codex CLI found."
    result = subprocess.run(
        [CODEX_BIN, "exec", "--sandbox", "workspace-write", "--skip-git-repo-check", "-C", str(scratch_dir), "-"],
        input=(scratch_dir / "_prompt.txt").read_text(encoding="utf-8"),
        capture_output=True, text=True, timeout=CODEX_CALL_TIMEOUT,
    )
    return result.returncode == 0, (result.stdout[-4000:] + "\n" + result.stderr[-4000:])


def convert_one(dsd: dict[str, Any], report_text: str, dest_dir: Path) -> dict[str, Any]:
    dest_dir.mkdir(parents=True, exist_ok=True)
    scratch = dest_dir / "_scratch"
    if scratch.exists():
        shutil.rmtree(scratch)
    scratch.mkdir(parents=True)
    (scratch / "report_text.txt").write_text(report_text, encoding="utf-8")
    prompt = build_prompt(dsd)
    (scratch / "_prompt.txt").write_text(prompt, encoding="utf-8")

    ok, codex_log = run_codex(scratch)
    generated_script = None
    script_path = scratch / "convert.py"
    if script_path.exists():
        generated_script = script_path.read_text(encoding="utf-8")
        (dest_dir / "convert.py").write_text(generated_script, encoding="utf-8")

    output_parquet = scratch / "output.parquet"
    if not ok or not output_parquet.exists():
        return {
            "status": "FAILED",
            "error": "codex exec did not produce output.parquet" if ok else "codex exec failed",
            "codex_log": codex_log,
            "script": generated_script,
        }

    try:
        import pandas as pd

        df = pd.read_parquet(output_parquet)
    except Exception as error:  # the file exists but isn't a valid/readable parquet
        return {
            "status": "FAILED",
            "error": f"Generated output.parquet could not be read: {type(error).__name__}: {error}",
            "codex_log": codex_log,
            "script": generated_script,
        }

    final_parquet = dest_dir / "output.parquet"
    shutil.copyfile(output_parquet, final_parquet)
    preview = {
        "columns": list(df.columns.astype(str)),
        "rows": df.head(PREVIEW_ROWS).astype(object).where(df.notna(), None).values.tolist(),
        "row_count": int(len(df)),
    }
    (dest_dir / "preview.json").write_text(json.dumps(preview, default=_json_default), encoding="utf-8")
    shutil.rmtree(scratch, ignore_errors=True)
    return {"status": "SUCCESS", "error": None, "script": generated_script, "preview": preview}


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--file", required=True, help="Filename relative to Inputs/")
    parser.add_argument("--dsd-json", required=True, help="Path to the DSD/Key Family JSON for this file")
    parser.add_argument("--status-file", required=True)
    args = parser.parse_args()

    stem = Path(args.file).stem
    text_path = TEXT_ROOT / f"{stem}.txt"
    if not text_path.exists():
        print(json.dumps({"error": f"Missing extracted text: {text_path}"}))
        return 1
    report_text = text_path.read_text(encoding="utf-8")
    dsd_data = json.loads(Path(args.dsd_json).read_text(encoding="utf-8"))

    status_path = Path(args.status_file)
    results: dict[str, Any] = {}
    for dsd in dsd_data.get("data_structures", []):
        dsd_id = dsd.get("dsd_id", "UNKNOWN_DSD")
        dest_dir = DATA_CONVERSIONS_ROOT / f"{stem}__{dsd_id}"
        results[dsd_id] = convert_one(dsd, report_text, dest_dir)
        status_path.write_text(json.dumps(results), encoding="utf-8")

    print(json.dumps({key: value["status"] for key, value in results.items()}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
