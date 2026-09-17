import { getDb } from "./db";
import type { ArtifactIdentity, ReviewItem } from "./types";
import type { RawArtifactEnvelopes } from "./realSdmxAdapter";

type SessionRow = {
  id: string;
  filenames: string;
  items_json: string;
  identities_json: string;
  raw_json: string;
  data_conversion_json: string;
};

export type DataConversionStatus = { status: string; error: string | null };

export function loadActiveSession():
  | {
      id: string;
      filenames: string[];
      items: ReviewItem[];
      identities: ArtifactIdentity[];
      raw: RawArtifactEnvelopes;
      dataConversion: Record<string, DataConversionStatus>;
    }
  | null {
  const db = getDb();
  const active = db.prepare(`SELECT session_id FROM active_session WHERE k = 1`).get() as
    | { session_id: string }
    | undefined;
  if (!active) return null;
  return loadSession(active.session_id);
}

export function loadSession(sessionId: string) {
  const db = getDb();
  const row = db
    .prepare(
      `SELECT id, filenames, items_json, identities_json, raw_json, data_conversion_json FROM sessions WHERE id = ?`,
    )
    .get(sessionId) as SessionRow | undefined;
  if (!row) return null;
  return {
    id: row.id,
    filenames: JSON.parse(row.filenames) as string[],
    items: JSON.parse(row.items_json) as ReviewItem[],
    identities: JSON.parse(row.identities_json || "[]") as ArtifactIdentity[],
    raw: JSON.parse(row.raw_json || "{}") as RawArtifactEnvelopes,
    dataConversion: JSON.parse(row.data_conversion_json || "{}") as Record<string, DataConversionStatus>,
  };
}
