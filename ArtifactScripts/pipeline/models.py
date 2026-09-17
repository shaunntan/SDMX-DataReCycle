from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, create_model, field_validator, model_validator

NonEmpty = Annotated[str, Field(min_length=1)]
Identifier = Annotated[str, Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]*$")]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class StandardReference(StrictModel):
    agency: NonEmpty
    artifact_type: NonEmpty
    artifact_id: NonEmpty
    version: NonEmpty
    url: NonEmpty
    evidence: NonEmpty
    verification_status: Literal["CONFIRMED", "CANDIDATE", "UNVERIFIED"]

    @field_validator("url")
    @classmethod
    def validate_url(cls, value: str) -> str:
        if not value.startswith(("https://", "http://")):
            raise ValueError("Reference URL must be HTTP(S)")
        return value


class BaseArtifact(StrictModel):
    artifact_type: NonEmpty
    source_report: NonEmpty
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    principles_file: NonEmpty
    principles_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    retrieved_chunk_ids: list[int]
    standard_references: list[StandardReference]
    limitations: list[str]


class Concept(StrictModel):
    concept_id: Identifier
    name: NonEmpty
    definition: NonEmpty
    context: NonEmpty
    recommended_representation: NonEmpty
    standard_source_agency: NonEmpty
    standard_scheme_id: NonEmpty
    standard_version: NonEmpty
    source_url: NonEmpty
    local_notes: NonEmpty
    evidence_quote: NonEmpty


class ConceptScheme(StrictModel):
    scheme_id: Identifier
    name: NonEmpty
    agency_id: Identifier
    version: NonEmpty
    concepts: Annotated[list[Concept], Field(min_length=1)]


class ConceptSchemeArtifact(BaseArtifact):
    concept_schemes: Annotated[list[ConceptScheme], Field(min_length=1)]


class Code(StrictModel):
    code: NonEmpty
    name: NonEmpty
    definition: NonEmpty
    parent_code: str | None
    status: Literal["ACTIVE", "DEPRECATED", "PROPOSED_LOCAL"]
    evidence_quote: NonEmpty
    local_creation_justification: str | None


class Codelist(StrictModel):
    codelist_id: Identifier
    name: NonEmpty
    agency_id: Identifier
    version: NonEmpty
    source_url: NonEmpty
    maintenance_status: Literal["AUTHORITATIVE_REFERENCE", "LOCAL_CONSTRAINT", "CANDIDATE_MAPPING", "PROPOSED_LOCAL"]
    verification_status: Literal["CONFIRMED", "CANDIDATE", "UNVERIFIED"]
    date_checked: NonEmpty
    scope_notes: NonEmpty
    codes: Annotated[list[Code], Field(min_length=1)]

    @model_validator(mode="after")
    def unique_codes(self):
        values = [item.code for item in self.codes]
        if len(values) != len(set(values)):
            raise ValueError("Codelist code IDs must be unique")
        return self


class CodelistsArtifact(BaseArtifact):
    codelists: Annotated[list[Codelist], Field(min_length=1)]


class Component(StrictModel):
    position: int | None
    concept_id: Identifier
    role: Literal["DIMENSION", "TIME", "MEASURE", "ATTRIBUTE"]
    representation: NonEmpty
    codelist_agency: str | None
    codelist_id: str | None
    codelist_version: str | None
    data_type: NonEmpty
    usage_status: Literal["MANDATORY", "CONDITIONAL", "OPTIONAL"]
    attachment_level: Literal["DATASET", "GROUP", "SERIES", "OBSERVATION"] | None
    notes: NonEmpty
    evidence_quote: NonEmpty


class DataStructure(StrictModel):
    dsd_id: Identifier
    name: NonEmpty
    agency_id: Identifier
    version: NonEmpty
    statistical_scope: NonEmpty
    components: Annotated[list[Component], Field(min_length=3)]

    @model_validator(mode="after")
    def valid_roles(self):
        roles = [item.role for item in self.components]
        if roles.count("TIME") != 1 or roles.count("MEASURE") != 1 or "DIMENSION" not in roles:
            raise ValueError("Each DSD needs dimensions, exactly one time component, and exactly one primary measure")
        return self


class DSDArtifact(BaseArtifact):
    data_structures: Annotated[list[DataStructure], Field(min_length=1)]
    structure_separation_rationale: NonEmpty


class Dataflow(StrictModel):
    dataflow_id: Identifier
    name: NonEmpty
    agency_id: Identifier
    version: NonEmpty
    dsd_id: Identifier
    dsd_agency_id: Identifier
    dsd_version: NonEmpty
    description: NonEmpty
    coverage: NonEmpty
    evidence_quote: NonEmpty


class DataflowArtifact(BaseArtifact):
    dataflows: Annotated[list[Dataflow], Field(min_length=1)]


class MetadataConcept(StrictModel):
    concept_id: Identifier
    name: NonEmpty
    definition: NonEmpty
    representation: NonEmpty
    required: bool
    usage_status: Literal["MANDATORY", "CONDITIONAL", "OPTIONAL"]
    target_attachment: Literal["REPORT", "DATAFLOW", "DATASET", "SERIES", "OBSERVATION", "METADATA"]
    extraction_guidance: NonEmpty
    source_standard: NonEmpty
    source_url: NonEmpty


class MetadataStructure(StrictModel):
    msd_id: Identifier
    name: NonEmpty
    agency_id: Identifier
    version: NonEmpty
    concepts: Annotated[list[MetadataConcept], Field(min_length=1)]


class MSDArtifact(BaseArtifact):
    metadata_structures: Annotated[list[MetadataStructure], Field(min_length=1)]


class MetadataValue(StrictModel):
    concept_id: Identifier
    value: NonEmpty
    evidence_quote: NonEmpty
    source_location: NonEmpty


class MetadataSet(StrictModel):
    metadata_set_id: Identifier
    msd_id: Identifier
    target_id: Identifier
    target_type: Literal["REPORT", "DATAFLOW", "DATASET", "SERIES", "OBSERVATION", "METADATA"]
    values: Annotated[list[MetadataValue], Field(min_length=1)]


class MetadataSetArtifact(BaseArtifact):
    metadata_sets: Annotated[list[MetadataSet], Field(min_length=1)]


class TemplateColumn(StrictModel):
    column_id: Identifier
    role: Literal["DIMENSION", "TIME", "MEASURE", "ATTRIBUTE"]
    required: bool
    data_type: NonEmpty
    codelist_id: str | None
    description: NonEmpty


class TemplateValue(StrictModel):
    column_id: Identifier
    value: str | int | float | None


class ObservationRow(StrictModel):
    dsd_id: Identifier
    values: Annotated[list[TemplateValue], Field(min_length=1)]
    evidence_quote: NonEmpty


class DataTemplate(StrictModel):
    template_id: Identifier
    dsd_id: Identifier
    columns: Annotated[list[TemplateColumn], Field(min_length=3)]
    observations: Annotated[list[ObservationRow], Field(min_length=1)]

    @model_validator(mode="after")
    def rows_match_columns(self):
        expected = {item.column_id for item in self.columns}
        if len(expected) != len(self.columns):
            raise ValueError("Template column IDs must be unique")
        for row in self.observations:
            actual = [item.column_id for item in row.values]
            if len(actual) != len(set(actual)) or set(actual) != expected:
                raise ValueError("Every observation row must contain each declared template column exactly once")
        return self


class AITemplateArtifact(BaseArtifact):
    templates: Annotated[list[DataTemplate], Field(min_length=1)]


class CodebookField(StrictModel):
    field_id: Identifier
    name: NonEmpty
    definition: NonEmpty
    role: Literal["DIMENSION", "TIME", "MEASURE", "ATTRIBUTE"]
    representation: NonEmpty
    codelist_id: str | None
    required: bool
    example: NonEmpty
    source_standard: NonEmpty
    source_url: NonEmpty


class SourceMapping(StrictModel):
    source_value: NonEmpty
    source_context: NonEmpty
    target_field: Identifier
    target_code: str | None
    target_code_label: str | None
    mapping_type: Literal["EXACT", "BROADER", "NARROWER", "DERIVED", "LOCAL_EQUIVALENT", "UNRESOLVED"]
    target_standard: NonEmpty
    notes: NonEmpty
    evidence_quote: NonEmpty


class CodebookMappingArtifact(BaseArtifact):
    fields: Annotated[list[CodebookField], Field(min_length=1)]
    source_value_mappings: Annotated[list[SourceMapping], Field(min_length=1)]
    unresolved: list[str]


class SemanticReview(StrictModel):
    valid: bool
    issues: list[str]
    repair_instructions: list[str]

    @model_validator(mode="after")
    def coherent(self):
        if self.valid and (self.issues or self.repair_instructions):
            raise ValueError("A valid review cannot contain issues or repair instructions")
        if not self.valid and not self.issues:
            raise ValueError("An invalid review must explain at least one issue")
        return self


class AggregateReview(StrictModel):
    valid: bool
    covered_source_reports: list[str]
    missing_source_reports: list[str]
    missing_requirements: list[str]
    redundancies_remaining: list[str]
    schema_issues: list[str]
    repair_instructions: list[str]

    @model_validator(mode="after")
    def coherent(self):
        issue_lists = (
            self.missing_source_reports, self.missing_requirements,
            self.redundancies_remaining, self.schema_issues,
        )
        if self.valid and (any(issue_lists) or self.repair_instructions):
            raise ValueError("An approved aggregate review cannot contain unresolved issues")
        if not self.valid and not any(issue_lists):
            raise ValueError("A rejected aggregate review must identify an issue")
        return self


class MultiplicityDecision(StrictModel):
    decision: Literal["SINGLE", "MULTIPLE"]
    artifact_count: Annotated[int, Field(ge=1)]
    artifact_ids: Annotated[list[Identifier], Field(min_length=1)]
    rationale: NonEmpty
    shared_components_strategy: NonEmpty

    @model_validator(mode="after")
    def count_matches(self):
        if self.artifact_count != len(self.artifact_ids):
            raise ValueError("artifact_count must equal the number of artifact_ids")
        if self.decision == "SINGLE" and self.artifact_count != 1:
            raise ValueError("SINGLE requires exactly one artifact")
        if self.decision == "MULTIPLE" and self.artifact_count < 2:
            raise ValueError("MULTIPLE requires at least two artifacts")
        return self


class FinalReview(StrictModel):
    valid: bool
    aggregate_requirements_covered: bool
    multiplicity_appropriate: bool
    best_practices_followed: bool
    missing_requirements: list[str]
    multiplicity_issues: list[str]
    best_practice_issues: list[str]
    schema_issues: list[str]
    repair_instructions: list[str]

    @model_validator(mode="after")
    def coherent(self):
        flags = self.aggregate_requirements_covered and self.multiplicity_appropriate and self.best_practices_followed
        issues = self.missing_requirements or self.multiplicity_issues or self.best_practice_issues or self.schema_issues
        if self.valid and (not flags or issues or self.repair_instructions):
            raise ValueError("A valid final review must pass every check without issues")
        if not self.valid and not issues:
            raise ValueError("An invalid final review must identify an issue")
        return self


MODEL_BY_KEY = {
    "CONCEPT_SCHEME": ConceptSchemeArtifact,
    "CODELISTS": CodelistsArtifact,
    "DSD_KEY_FAMILY": DSDArtifact,
    "DATAFLOW": DataflowArtifact,
    "METADATA_STRUCTURE_DEFINITION_MSD": MSDArtifact,
    "METADATA_SET": MetadataSetArtifact,
    "AI_FILLABLE_DATA_TEMPLATE": AITemplateArtifact,
    "CODEBOOK_AND_SOURCE_MAPPING": CodebookMappingArtifact,
}


def model_for(key: str) -> type[BaseArtifact]:
    if key not in MODEL_BY_KEY:
        raise KeyError(f"No Pydantic model registered for discovered artifact {key}. Add it to Codes/pipeline/models.py")
    return MODEL_BY_KEY[key]


_FINAL_MODEL_CACHE: dict[str, type[StrictModel]] = {}


def final_envelope_model(key: str) -> type[StrictModel]:
    if key not in _FINAL_MODEL_CACHE:
        artifact_model = model_for(key)
        _FINAL_MODEL_CACHE[key] = create_model(
            f"Final{artifact_model.__name__}Envelope",
            __base__=StrictModel,
            artifact_key=(NonEmpty, ...),
            artifact_name=(NonEmpty, ...),
            source_aggregate_sha256=(Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")], ...),
            principles_sha256=(Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")], ...),
            best_practice_chunk_ids=(list[int], ...),
            multiplicity_decision=(MultiplicityDecision, ...),
            final_artifact=(artifact_model, ...),
        )
    return _FINAL_MODEL_CACHE[key]
