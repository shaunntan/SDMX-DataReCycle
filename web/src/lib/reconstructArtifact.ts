import type { ArtifactIdentity, ArtifactType, ReviewItem } from "./types";
import type { RawArtifactEnvelopes } from "./realSdmxAdapter";

/**
 * Rebuilds one full, SDMX-schema-shaped artifact object (a single Codelist /
 * ConceptScheme / DataStructure) for structural validation and export,
 * starting from the pipeline's original real JSON (which carries every field
 * the Pydantic schemas require -- evidence_quote, context, status enums,
 * etc.) and overlaying only the fields the curator actually reviewed
 * (name/definition, or role/codelist_id/usage_status/data_type) plus the
 * confirmed Agency ID / Version / Name identity.
 *
 * Only fields already exposed in the Review UI are overlaid; everything else
 * on the matched raw object (evidence_quote, context, standard_source_agency,
 * status, ...) is preserved untouched so the reconstructed object still
 * satisfies the strict Pydantic schemas in PrototypeCodes/pipeline/models.py.
 */

type JsonRecord = Record<string, unknown>;

function effectiveValue(item: ReviewItem): string | null {
  return item.status === "edited" ? item.edited_value : item.suggested_value;
}

export function reconstructArtifact(
  raw: RawArtifactEnvelopes,
  artifactType: ArtifactType,
  artifactId: string,
  items: ReviewItem[],
  identity: ArtifactIdentity,
): JsonRecord | null {
  const itemsForArtifact = items.filter((i) => i.artifact_id === artifactId);
  const byItemAndField = new Map<string, ReviewItem>();
  for (const item of itemsForArtifact) byItemAndField.set(`${item.item_id}::${item.field}`, item);

  function overlay(target: JsonRecord, itemId: string, fields: string[]): JsonRecord {
    const clone: JsonRecord = { ...target };
    for (const field of fields) {
      const item = byItemAndField.get(`${itemId}::${field}`);
      if (item) clone[field] = effectiveValue(item);
    }
    return clone;
  }

  if (artifactType === "conceptscheme") {
    const envelope = raw.conceptscheme;
    const scheme = ((envelope?.concept_schemes as JsonRecord[] | undefined) ?? []).find(
      (s) => String(s.scheme_id) === artifactId,
    );
    if (!scheme) return null;
    const concepts = ((scheme.concepts as JsonRecord[] | undefined) ?? []).map((concept) =>
      overlay(concept, String(concept.concept_id), ["name", "definition"]),
    );
    return { ...scheme, concepts, name: identity.name, agency_id: identity.agency_id, version: identity.version };
  }

  if (artifactType === "codelist") {
    const envelope = raw.codelist;
    const codelist = ((envelope?.codelists as JsonRecord[] | undefined) ?? []).find(
      (c) => String(c.codelist_id) === artifactId,
    );
    if (!codelist) return null;
    const codes = ((codelist.codes as JsonRecord[] | undefined) ?? []).map((code) =>
      overlay(code, String(code.code), ["name", "definition"]),
    );
    return { ...codelist, codes, name: identity.name, agency_id: identity.agency_id, version: identity.version };
  }

  if (artifactType === "dsd") {
    const envelope = raw.dsd;
    const structure = ((envelope?.data_structures as JsonRecord[] | undefined) ?? []).find(
      (s) => String(s.dsd_id) === artifactId,
    );
    if (!structure) return null;
    const components = ((structure.components as JsonRecord[] | undefined) ?? []).map((component) =>
      overlay(component, String(component.concept_id), ["role", "codelist_id", "usage_status", "data_type"]),
    );
    return { ...structure, components, name: identity.name, agency_id: identity.agency_id, version: identity.version };
  }

  const envelope = raw.dataflow;
  const flow = ((envelope?.dataflows as JsonRecord[] | undefined) ?? []).find(
    (f) => String(f.dataflow_id) === artifactId,
  );
  if (!flow) return null;
  const overlaid = overlay(flow, artifactId, ["description", "coverage", "dsd_id"]);
  return { ...overlaid, name: identity.name, agency_id: identity.agency_id, version: identity.version };
}
