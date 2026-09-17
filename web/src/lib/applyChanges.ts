import type Database from "better-sqlite3";
import type { ReviewItem, SuggestedChange } from "@/lib/types";

/**
 * Apply accepted suggested changes onto one saved artifact's review items:
 * mark each matching item edited, log it to applied_changes, and write the
 * items back. Returns the number of changes actually applied (changes whose
 * item_id/field don't match an item on that row are skipped).
 *
 * Runs in its own transaction; shared by /api/ai-review/apply (one row) and
 * /api/export/apply (many rows).
 */
export function applyChangesToArtifact(
  db: Database.Database,
  savedArtifactId: number,
  changes: SuggestedChange[],
): number | null {
  const row = db
    .prepare(`SELECT items_json FROM saved_artifacts WHERE id = ?`)
    .get(savedArtifactId) as { items_json: string } | undefined;
  if (!row) return null;

  const items = JSON.parse(row.items_json) as ReviewItem[];
  const log = db.prepare(
    `INSERT INTO applied_changes (saved_artifact_id, change_id, item_id, field, old_value, new_value, applied_at)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
  );

  let applied = 0;
  const tx = db.transaction(() => {
    for (const c of changes) {
      const target = items.find((i) => i.item_id === c.item_id && i.field === c.field);
      if (!target) continue;
      const old = target.status === "edited" ? target.edited_value : target.suggested_value;
      target.status = "edited";
      target.edited_value = c.suggested_value;
      log.run(
        savedArtifactId,
        c.change_id,
        c.item_id,
        c.field,
        old,
        c.suggested_value,
        new Date().toISOString(),
      );
      applied++;
    }
    db.prepare(`UPDATE saved_artifacts SET items_json = ? WHERE id = ?`).run(
      JSON.stringify(items),
      savedArtifactId,
    );
  });
  tx();

  return applied;
}
