import { getDb } from "@/lib/db";
import type { ArtifactType, ReviewItem } from "@/lib/types";

export type SavedArtifactReviewRow = {
  id: number;
  artifact_type: ArtifactType;
  artifact_id: string;
  version: string;
  name: string;
  agency_id: string;
  items_json: string;
};

export type AiReviewStdin = {
  artifact_type: ArtifactType;
  artifact_identity: {
    artifact_type: ArtifactType;
    artifact_id: string;
    name: string;
    agency_id: string;
    version: string;
  };
  items: ReviewItem[];
};

/**
 * Loads a saved artifact and builds the stdin payload for ai_review.py, shared
 * by /api/ai-review (real call) and /api/ai-review/prompt (dry run).
 */
export function loadAiReviewPayload(
  savedArtifactId: number,
): { row: SavedArtifactReviewRow; items: ReviewItem[]; stdin: AiReviewStdin } | null {
  const row = getDb()
    .prepare(
      `SELECT id, artifact_type, artifact_id, version, name, agency_id, items_json
       FROM saved_artifacts WHERE id = ?`,
    )
    .get(savedArtifactId) as SavedArtifactReviewRow | undefined;
  if (!row) return null;

  const items = JSON.parse(row.items_json) as ReviewItem[];
  return {
    row,
    items,
    stdin: {
      artifact_type: row.artifact_type,
      artifact_identity: {
        artifact_type: row.artifact_type,
        artifact_id: row.artifact_id,
        name: row.name,
        agency_id: row.agency_id,
        version: row.version,
      },
      items,
    },
  };
}
