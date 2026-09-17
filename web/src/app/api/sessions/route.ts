import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";

export const runtime = "nodejs";

/** Every processed file's review session ("set"), for the Processed Files list. */
export async function GET() {
  const db = getDb();
  const rows = db
    .prepare(`SELECT id, created_at, filenames FROM sessions ORDER BY created_at DESC`)
    .all() as Array<{ id: string; created_at: string; filenames: string }>;
  const active = db.prepare(`SELECT session_id FROM active_session WHERE k = 1`).get() as
    | { session_id: string }
    | undefined;

  return NextResponse.json({
    sessions: rows.map((r) => ({
      id: r.id,
      created_at: r.created_at,
      filenames: JSON.parse(r.filenames) as string[],
      active: r.id === active?.session_id,
    })),
  });
}
