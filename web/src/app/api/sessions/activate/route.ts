import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { loadSession } from "@/lib/session";

export const runtime = "nodejs";

/** Reopens a past processed file's set for review/edits. */
export async function POST(req: Request) {
  const body = (await req.json()) as { session_id: string };
  const session = loadSession(body.session_id);
  if (!session) {
    return NextResponse.json({ error: "Unknown session" }, { status: 404 });
  }
  const db = getDb();
  db.prepare(
    `INSERT INTO active_session (k, session_id) VALUES (1, ?)
     ON CONFLICT(k) DO UPDATE SET session_id = excluded.session_id`,
  ).run(body.session_id);
  return NextResponse.json({ ok: true });
}
