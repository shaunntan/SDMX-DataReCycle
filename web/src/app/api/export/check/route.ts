import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { checkCrossReferencesAndIdentity, type SavedArtifactRow } from "@/lib/exportChecks";
import { runStructuralValidation } from "@/lib/structuralValidation";

export const runtime = "nodejs";

/**
 * Export consistency check (warn, doesn't block export):
 *  - cross-reference integrity + identity/version coherence (Node, exportChecks.ts)
 *  - real SDMX-ML structural validity, by reusing the pipeline's own Pydantic
 *    schemas via validate_export.py (see that file for why)
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { ids: number[] };
  const ids = body.ids ?? [];
  if (!ids.length) {
    return NextResponse.json({ error: "No artifacts selected" }, { status: 400 });
  }

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
      // Skip artifacts saved before structured_json existed; nothing to
      // structurally validate for them.
    }
  }
  const structural = await runStructuralValidation(grouped);

  return NextResponse.json({
    reference_issues: referenceIssues,
    structural: structural ?? null,
    structural_unavailable: structural === null,
  });
}
