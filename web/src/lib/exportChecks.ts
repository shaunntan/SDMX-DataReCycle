type JsonRecord = Record<string, unknown>;

export type SavedArtifactRow = {
  id: number;
  artifact_type: "conceptscheme" | "codelist" | "dsd" | "dataflow";
  artifact_id: string;
  version: string;
  name: string;
  agency_id: string;
  structured_json: string;
};

/**
 * Cross-reference integrity + identity/version coherence checks across a set
 * of selected saved artifacts. These aren't covered by the pipeline's own
 * cross_artifact_issues() (it only checks DATAFLOW/METADATA_SET/AI template/
 * codebook references, not DSD -> Codelist/Concept Scheme), so they're
 * implemented directly here against the reconstructed structured objects.
 */
export function checkCrossReferencesAndIdentity(rows: SavedArtifactRow[]): string[] {
  const issues: string[] = [];

  const byTriple = new Map<string, SavedArtifactRow[]>();
  for (const row of rows) {
    const key = `${row.artifact_type}::${row.agency_id}::${row.artifact_id}::${row.version}`;
    if (!byTriple.has(key)) byTriple.set(key, []);
    byTriple.get(key)!.push(row);
  }
  for (const [key, group] of byTriple) {
    if (group.length > 1) {
      issues.push(
        `Duplicate identity: ${group.length} selected artifacts share Agency/ID/Version "${key.replaceAll("::", " / ")}" -- versions should be distinct.`,
      );
    }
  }

  const codelistsById = new Map(
    rows.filter((r) => r.artifact_type === "codelist").map((r) => [r.artifact_id, r]),
  );
  const conceptIdsByScheme = new Map<string, Set<string>>();
  for (const row of rows.filter((r) => r.artifact_type === "conceptscheme")) {
    const structured = JSON.parse(row.structured_json) as JsonRecord;
    const concepts = (structured.concepts as JsonRecord[] | undefined) ?? [];
    conceptIdsByScheme.set(row.artifact_id, new Set(concepts.map((c) => String(c.concept_id))));
  }
  const allConceptIds = new Set([...conceptIdsByScheme.values()].flatMap((s) => [...s]));

  for (const row of rows.filter((r) => r.artifact_type === "dsd")) {
    const structured = JSON.parse(row.structured_json) as JsonRecord;
    const components = (structured.components as JsonRecord[] | undefined) ?? [];
    for (const component of components) {
      const codelistId = component.codelist_id as string | null | undefined;
      const conceptId = String(component.concept_id ?? "");
      if (codelistId) {
        const referenced = codelistsById.get(codelistId);
        if (!referenced) {
          issues.push(
            `DSD "${row.artifact_id}" component "${conceptId}" references codelist "${codelistId}", which isn't in the export selection.`,
          );
        } else if (component.codelist_version && component.codelist_version !== referenced.version) {
          issues.push(
            `DSD "${row.artifact_id}" component "${conceptId}" expects codelist "${codelistId}" v${component.codelist_version}, but the selected version is v${referenced.version}.`,
          );
        }
      }
      if (allConceptIds.size > 0 && !allConceptIds.has(conceptId)) {
        issues.push(
          `DSD "${row.artifact_id}" component "${conceptId}" doesn't match any concept in the selected Concept Scheme(s).`,
        );
      }
    }
  }

  const dsdById = new Map(rows.filter((r) => r.artifact_type === "dsd").map((r) => [r.artifact_id, r]));
  for (const row of rows.filter((r) => r.artifact_type === "dataflow")) {
    const structured = JSON.parse(row.structured_json) as JsonRecord;
    const dsdId = structured.dsd_id as string | null | undefined;
    if (dsdId) {
      const referenced = dsdById.get(dsdId);
      if (!referenced) {
        issues.push(`Dataflow "${row.artifact_id}" references DSD "${dsdId}", which isn't in the export selection.`);
      } else if (structured.dsd_version && structured.dsd_version !== referenced.version) {
        issues.push(
          `Dataflow "${row.artifact_id}" expects DSD "${dsdId}" v${structured.dsd_version}, but the selected version is v${referenced.version}.`,
        );
      }
    }
  }

  return issues;
}
