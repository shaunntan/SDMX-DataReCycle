import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { applyChangesToArtifact } from "@/lib/applyChanges";
import type { SuggestedChange } from "@/lib/types";

export const runtime = "nodejs";

type ExportChange = SuggestedChange & { saved_artifact_id: number };

/**
 * Persist accepted export-fix suggestions. Unlike /api/ai-review/apply, an
 * export selection can span several saved artifacts, so each change carries
 * the saved_artifact_id it belongs to and changes are applied per row.
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { changes: ExportChange[] };
  const changes = body.changes ?? [];

  const byArtifact = new Map<number, ExportChange[]>();
  for (const change of changes) {
    if (!byArtifact.has(change.saved_artifact_id)) byArtifact.set(change.saved_artifact_id, []);
    byArtifact.get(change.saved_artifact_id)!.push(change);
  }

  const db = getDb();
  let applied = 0;
  for (const [savedArtifactId, group] of byArtifact) {
    // A missing row (null) just contributes nothing, as with an unmatched item.
    applied += applyChangesToArtifact(db, savedArtifactId, group) ?? 0;
  }

  return NextResponse.json({ ok: true, applied });
}
