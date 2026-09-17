import { getDb } from "@/lib/db";
import { checkCrossReferencesAndIdentity, type SavedArtifactRow } from "@/lib/exportChecks";
import { runStructuralValidation } from "@/lib/structuralValidation";

export type ExportSuggestStdin = {
  artifact_types: string[];
  artifacts_json: Record<string, unknown[]>;
  reference_issues: string[];
  structural_errors: string[];
};

/**
 * Reruns the export reference + structural checks for the selected artifacts
 * and builds the stdin payload for export_suggest.py, shared by
 * /api/export/suggest (real call) and /api/export/suggest/prompt (dry run).
 */
export async function buildExportSuggestPayload(ids: number[]): Promise<ExportSuggestStdin> {
  const db = getDb();
  const placeholders = ids.map(() => "?").join(",");
  const rows = db
    .prepare(
      `SELECT id, artifact_type, artifact_id, version, name, agency_id, structured_json
       FROM saved_artifacts WHERE id IN (${placeholders})`,
    )
    .all(...ids) as SavedArtifactRow[];

  const referenceIssues = checkCrossReferencesAndIdentity(rows);

  const grouped: Record<string, unknown[]> = { conceptscheme: [], codelist: [], dsd: [], dataflow: [] };
  for (const row of rows) {
    try {
      grouped[row.artifact_type].push(JSON.parse(row.structured_json));
    } catch {
      // Skip artifacts saved before structured_json existed.
    }
  }
  const structural = await runStructuralValidation(grouped);
  const structuralErrors = Object.values(structural ?? {}).flatMap((r) => r.errors);

  return {
    artifact_types: [...new Set(rows.map((r) => r.artifact_type))],
    artifacts_json: grouped,
    reference_issues: referenceIssues,
    structural_errors: structuralErrors,
  };
}
