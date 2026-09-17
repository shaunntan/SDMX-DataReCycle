import { getDb } from "@/lib/db";
import { ARTIFACT_LABEL, effectiveValue, type ArtifactType, type ReviewItem } from "@/lib/types";

export const runtime = "nodejs";

/**
 * STUB: real implementation would build a proper SDMX-ML zip.
 * Here we return a plain-text "archive" describing the selection.
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { ids: number[] };
  const ids = body.ids ?? [];
  if (!ids.length) {
    return new Response("No artifacts selected", { status: 400 });
  }

  await new Promise((r) => setTimeout(r, 600));

  const db = getDb();
  const placeholders = ids.map(() => "?").join(",");
  const rows = db
    .prepare(
      `SELECT id, artifact_type, artifact_id, version, saved_at, items_json
       FROM saved_artifacts WHERE id IN (${placeholders})`,
    )
    .all(...ids) as Array<{
    id: number;
    artifact_type: ArtifactType;
    artifact_id: string;
    version: string;
    saved_at: string;
    items_json: string;
  }>;

  const lines: string[] = [
    "SDMX EXPORT BUNDLE (mock archive - not a real zip)",
    `Generated: ${new Date().toISOString()}`,
    `Artifacts: ${rows.length}`,
    "",
  ];
  for (const r of rows) {
    lines.push("=".repeat(60));
    lines.push(`${ARTIFACT_LABEL[r.artifact_type]} / ${r.artifact_id} v${r.version}`);
    lines.push(`saved_at: ${r.saved_at}`);
    lines.push("-".repeat(60));
    const items = JSON.parse(r.items_json) as ReviewItem[];
    for (const it of items) {
      lines.push(`  ${it.item_id}.${it.field} = ${effectiveValue(it) ?? ""}`);
    }
    lines.push("");
  }

  const stamp = new Date().toISOString().replace(/[-:T]/g, "").slice(0, 14);
  return new Response(lines.join("\n"), {
    headers: {
      "Content-Type": "application/octet-stream",
      "Content-Disposition": `attachment; filename="sdmx_export_${stamp}.zip.txt"`,
    },
  });
}
