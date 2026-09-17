# Resumable report-to-SDMX pipeline

Run the full pipeline from the project root:

```powershell
python Codes\run_pipeline.py
```

The command discovers supported reports under `Inputs/`, generated artifacts under
`Artifact Principles/`, and resumes from `pipeline_control.xlsx`. It writes semantic
TXT to `Inputs_TXT/`, local FastEmbed vectors and chunk metadata to
`Inputs_Embeddings/`, and validated JSON plus human-editable companion CSV files to
`Artifact JSON/`. After per-report work it incrementally optimizes one aggregate per
artifact as `_aggregate.json` and validates coverage with an independent inspector.

SDMX XML files placed in `Inputs XML/` are parsed mechanically without an AI call.
The namespace-agnostic converter supports the SDMX 2.0, 2.1, and 3.0 patterns in the
supplied full-case bundles and emits the same eight strict JSON/CSV artifact types.
They are registered in `pipeline_control.xlsx` with `SOURCE_KIND=XML`, while report
rows use `SOURCE_KIND=REPORT`. XML and report artifacts enter the same consistency,
aggregation, optimization, and finalization stages.

After finalization, a deterministic export stage combines all approved final artifacts
into `final SMDX structures/final_sdmx_2_1_structures.xml` and
`final SMDX structures/final_sdmx_3_0_structures.xml`. These exports follow the
supplied full-case bundle pattern and are tracked independently in the workbook's
`XML Export Control` sheet.
All text files in `Artifact Principles/` are embedded locally and relevant passages
from the full principles corpus are supplied to both the aggregate optimizer and its
inspector. Every completed aggregate then runs a two-agent final design stage that
decides whether one or multiple artifacts are appropriate. Strict final JSON files go
to `Final Artifacts/`; one readable leaf-value CSV per artifact goes to
`Final CSV Versions of Artifacts/`.

The companion CSV format uses `JSON_PATH`, `FIELD`, `VALUE_TYPE`, and `VALUE`. It is
round-trippable: edits made to either JSON or CSV are detected by timestamps,
Pydantic-validated, preserved as `MODIFIED`, and included in the next aggregate update.
Agent review uses two rounds: generation/review, correction/review, then the reviewer
directly applies any final changes. Each structured response still receives up to
three schema-validation attempts. A correction that cannot pass its schema is recorded
as `FAILED` in `pipeline_control.xlsx`, and processing continues with the next case.

Before aggregation, a mandatory cross-artifact consistency gate checks references
using this authority order: Concept Scheme/Codelists, DSD, Dataflow, MSD, Metadata
Set, AI template, then Codebook. A lower-authority artifact that disagrees is
regenerated with the exact issue and all authoritative upstream JSON in context.
Aggregation runs only after every report passes a fresh consistency audit.

Useful options are `--file`, `--artifact`, `--force`, `--refresh-standards`,
`--skip-aggregate`, and `--aggregate-only`.

Run only per-report stages:

```powershell
python Codes\run_pipeline.py --skip-aggregate
```

Update aggregates from already completed per-report artifacts:

```powershell
python Codes\run_pipeline.py --aggregate-only
```
Legacy `.doc` and `.ppt` inputs use LibreOffice when `soffice` is available. All
other listed formats use Python open-source readers. The local Azure configuration
is `Codes/config/Keys.json`; it is ignored here and must never be committed.
