SDMX REPORT-TO-STRUCTURE GUIDE PACKAGE
======================================

Purpose
-------
This package is a practical reference for taking an arbitrary statistical report
(PDF, Word, Excel, CSV, HTML, or mixed material), inferring one or more statistical
structures from it, and preparing templates that an AI can later populate.

Target standard
---------------
SDMX 2.0.

In SDMX 2.0, the formal name of a DSD is "Key Family". This package often writes
"DSD / Key Family" because DSD is the term most practitioners now recognise.

Minimum package used here
-------------------------
1. Concept Scheme
2. Codelists
3. DSD / Key Family
4. Dataflow
5. Metadata Structure Definition (MSD)
6. Metadata Set
7. AI-fillable data template
8. Codebook and source-to-SDMX mapping

Reference files
---------------
- COMMON_SDMX_CONCEPTS_AND_CODE_SOURCES: reusable field/concept candidates such as
  REF_AREA, FREQ, TIME_PERIOD, OBS_VALUE, OBS_STATUS, UNIT_MULT, SEX, etc.
- SOURCE_REFERENCE_CATALOG: authoritative places to search before creating codes.

Core design rule
----------------
The report is evidence, not the target structure.

Do not create one DSD per table automatically. A report may contain several tables
that share one statistical structure, and it may also contain genuinely different
structures that require different DSDs.

Reuse rule
----------
Before creating any new concept, codelist or code:
1. Search SDMX common/cross-domain artefacts.
2. Search the SDMX Global Registry.
3. Search the authoritative international classification for the subject.
4. Search domain-specific international organisations and existing SDMX structures.
5. Search relevant national/institutional classifications.
6. Only then create a local artefact, documenting why no suitable reuse existed.

Semantic equivalence matters more than matching labels. Two codes called "TOTAL"
are not necessarily the same statistical concept.

How the package fits together
-----------------------------
REPORT
  |
  +--> Concept Scheme -------- defines meanings
  |
  +--> Codelists ------------- defines allowed coded values
  |
  +--> DSD / Key Family ------ defines dimensions, measure, attributes
  |       |
  |       +--> Dataflow ------ identifies a logical dataset using that DSD
  |
  +--> MSD ------------------- defines the structure of reference metadata
  |       |
  |       +--> Metadata Set -- contains actual methodology/source/caveat values
  |
  +--> AI data template ------ practical rows to be filled
          |
          +--> Codebook/mapping -- definitions, codes, source terminology mappings

What is deliberately NOT in the minimum package
------------------------------------------------
Constraints, Category Schemes/Reporting Taxonomies, Metadataflows, Provision
Agreements, Structure Sets, Organisation Schemes and formal process definitions
may be valuable later, but they are not required to begin the report-to-template
workflow.

CORE OFFICIAL SOURCES (checked 2026-09-16)
-----------------------------------------------
SDMX 2.0 standards landing page
https://sdmx.org/startpage/sdmx-standards-version-20/

SDMX 2.0 Information Model
https://sdmx.org/wp-content/uploads/SDMX_2_0_SECTION_02_InformationModel.pdf

SDMX 2.0 Implementor's Guide
https://sdmx.org/wp-content/uploads/SDMX_2_0_SECTION_06_ImplementorsGuide.pdf

SDMX Guidelines
https://sdmx.org/guidelines/

Guidelines for the Design of Data Structure Definitions
https://sdmx.org/wp-content/uploads/SDMX_Guidelines_for_DSDs_1.0.pdf

SDMX Glossary 2.1
https://sdmx.org/wp-content/uploads/SDMX_Glossary_Version_2_1_December_2020.htm

Standardising Reference Metadata Reporting in SDMX
https://sdmx.org/wp-content/uploads/Standardising-Reference-Metadata-Reporting-in-SDMX-v1-0.pdf

SDMX Global Registry - Codelists
https://registry.sdmx.org/items/codelist.html

IMPORTANT
---------
This package targets SDMX 2.0 as requested. In SDMX 2.0 the formal term for a
Data Structure Definition is "Key Family". Later SDMX statistical guidelines are
used here only for modelling good practice where the recommendation is compatible
with the SDMX 2.0 information model.
