import fs from "node:fs";
import path from "node:path";
import type { ArtifactIdentity, ReviewItem } from "./types";
import { STEP_ARTIFACT_FOLDER } from "./pipelineSteps";

/**
 * Adapts the REAL pipeline's per-artifact-type JSON (PrototypeCodes/pipeline,
 * written to "<repoRoot>/Artifact JSON/<Type>/<stem>.json") into the existing
 * flat ReviewItem[] shape the Review page already renders.
 *
 * Only the 4 artifact types the frontend currently models are covered here
 * (Concept Scheme, Codelists, DSD/Key Family, Dataflow) -- the pipeline also
 * produces MSD, Metadata Set, AI Fillable Data Template, and Codebook and
 * Source Mapping, but those aren't wired into Review yet (see
 * sdmx/review_requirements.md's proposed follow-up work).
 */

type JsonRecord = Record<string, unknown>;

function readArtifactJson(repoRoot: string, folder: string, stem: string): JsonRecord | null {
  const file = path.join(repoRoot, "Artifact JSON", folder, `${stem}.json`);
  if (!fs.existsSync(file)) return null;
  return JSON.parse(fs.readFileSync(file, "utf-8")) as JsonRecord;
}

let counter = 0;
function nextReviewId(): string {
  counter += 1;
  return `rv-real-${Date.now()}-${counter}`;
}

function row(
  artifact_type: ReviewItem["artifact_type"],
  artifact_id: string,
  item_id: string,
  item_label: string,
  parent_id: string | null,
  field: string,
  value: unknown,
): ReviewItem | null {
  if (value === null || value === undefined) return null;
  return {
    review_id: nextReviewId(),
    artifact_type,
    artifact_id,
    item_id,
    item_label,
    parent_id,
    field,
    suggested_value: String(value),
    current_value: null,
    status: "pending",
    edited_value: null,
  };
}

function identity(
  artifact_type: ReviewItem["artifact_type"],
  artifact_id: string,
  source: JsonRecord,
): ArtifactIdentity {
  return {
    artifact_type,
    artifact_id,
    name: source.name != null ? String(source.name) : artifact_id,
    agency_id: source.agency_id != null ? String(source.agency_id) : "",
    version: source.version != null ? String(source.version) : "",
  };
}

export type RawArtifactEnvelopes = {
  conceptscheme: JsonRecord | null;
  codelist: JsonRecord | null;
  dsd: JsonRecord | null;
  dataflow: JsonRecord | null;
};

export function buildReviewItemsFromRealArtifacts(
  repoRoot: string,
  stem: string,
): { items: ReviewItem[]; identities: ArtifactIdentity[]; raw: RawArtifactEnvelopes } {
  const items: ReviewItem[] = [];
  const identities: ArtifactIdentity[] = [];

  const conceptScheme = readArtifactJson(repoRoot, STEP_ARTIFACT_FOLDER.CONCEPT_SCHEME, stem);
  const schemes = (conceptScheme?.concept_schemes as JsonRecord[] | undefined) ?? [];
  for (const scheme of schemes) {
    const schemeId = String(scheme.scheme_id ?? "UNKNOWN_SCHEME");
    identities.push(identity("conceptscheme", schemeId, scheme));
    const concepts = (scheme.concepts as JsonRecord[] | undefined) ?? [];
    for (const concept of concepts) {
      const conceptId = String(concept.concept_id ?? "UNKNOWN_CONCEPT");
      const label = String(concept.name ?? conceptId);
      for (const field of ["name", "definition"]) {
        const item = row("conceptscheme", schemeId, conceptId, label, null, field, concept[field]);
        if (item) items.push(item);
      }
    }
  }

  const codelists = readArtifactJson(repoRoot, STEP_ARTIFACT_FOLDER.CODELISTS, stem);
  const lists = (codelists?.codelists as JsonRecord[] | undefined) ?? [];
  for (const codelist of lists) {
    const codelistId = String(codelist.codelist_id ?? "UNKNOWN_CODELIST");
    identities.push(identity("codelist", codelistId, codelist));
    const codes = (codelist.codes as JsonRecord[] | undefined) ?? [];
    for (const code of codes) {
      const codeId = String(code.code ?? "UNKNOWN_CODE");
      const label = String(code.name ?? codeId);
      const parentId = code.parent_code != null ? String(code.parent_code) : null;
      for (const field of ["name", "definition"]) {
        const item = row("codelist", codelistId, codeId, label, parentId, field, code[field]);
        if (item) items.push(item);
      }
    }
  }

  const dsd = readArtifactJson(repoRoot, STEP_ARTIFACT_FOLDER.DSD_KEY_FAMILY, stem);
  const structures = (dsd?.data_structures as JsonRecord[] | undefined) ?? [];
  for (const structure of structures) {
    const dsdId = String(structure.dsd_id ?? "UNKNOWN_DSD");
    identities.push(identity("dsd", dsdId, structure));
    const components = (structure.components as JsonRecord[] | undefined) ?? [];
    for (const component of components) {
      const conceptId = String(component.concept_id ?? "UNKNOWN_COMPONENT");
      const role = String(component.role ?? "");
      const label = role ? `${conceptId} (${role})` : conceptId;
      for (const field of ["role", "codelist_id", "usage_status", "data_type"]) {
        const item = row("dsd", dsdId, conceptId, label, null, field, component[field]);
        if (item) items.push(item);
      }
    }
  }

  const dataflowEnvelope = readArtifactJson(repoRoot, STEP_ARTIFACT_FOLDER.DATAFLOW, stem);
  const dataflows = (dataflowEnvelope?.dataflows as JsonRecord[] | undefined) ?? [];
  for (const flow of dataflows) {
    const flowId = String(flow.dataflow_id ?? "UNKNOWN_DATAFLOW");
    identities.push(identity("dataflow", flowId, flow));
    const label = String(flow.name ?? flowId);
    for (const field of ["description", "coverage", "dsd_id"]) {
      const item = row("dataflow", flowId, flowId, label, null, field, flow[field]);
      if (item) items.push(item);
    }
  }

  return {
    items,
    identities,
    raw: { conceptscheme: conceptScheme, codelist: codelists, dsd, dataflow: dataflowEnvelope },
  };
}
