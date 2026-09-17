export type ArtifactType = "codelist" | "conceptscheme" | "dsd" | "dataflow";

export type ReviewStatus = "pending" | "accepted" | "edited";

export type ReviewItem = {
  review_id: string;
  artifact_type: ArtifactType;
  artifact_id: string;
  item_id: string;
  item_label: string;
  parent_id: string | null;
  field: string;
  suggested_value: string | null;
  current_value: string | null;
  status: ReviewStatus;
  edited_value: string | null;
};

export const ARTIFACT_LABEL: Record<ArtifactType, string> = {
  dsd: "DSD",
  codelist: "Codelist",
  conceptscheme: "Concept Scheme",
  dataflow: "Dataflow",
};

/** Value that should be persisted for a review item. */
export function effectiveValue(item: ReviewItem): string | null {
  return item.status === "edited" ? item.edited_value : item.suggested_value;
}

/**
 * SDMX identity/governance fields for one maintainable artifact (one distinct
 * codelist / concept scheme / DSD within a set). Per the SDMX Information
 * Model, Agency ID + Artifact ID + Version form the artifact's identity and
 * are governance decisions an AI extraction cannot make on its own -- they
 * come out as placeholders (e.g. agency "SYNTHETIC_LABOUR_OBSERVATORY",
 * version "1.0-draft") and a human curator must confirm/set them before
 * saving. Name is lower-risk but still editable.
 */
export type ArtifactIdentity = {
  artifact_type: ArtifactType;
  artifact_id: string;
  name: string;
  agency_id: string;
  version: string;
};

export type SuggestedChange = {
  change_id: string;
  artifact_type: ArtifactType;
  artifact_id: string;
  item_id: string;
  field: string;
  current_value: string | null;
  suggested_value: string | null;
  rationale: string;
};
