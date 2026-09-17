import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { loadActiveSession } from "@/lib/session";
import type { ArtifactIdentity, ReviewItem } from "@/lib/types";

export const runtime = "nodejs";

export async function GET() {
  const s = loadActiveSession();
  if (!s) return NextResponse.json({ session: null });
  return NextResponse.json({ session: s });
}

/** Persist the in-progress review state (statuses / edited values / identity edits). */
export async function PUT(req: Request) {
  const body = (await req.json()) as {
    session_id: string;
    items?: ReviewItem[];
    identities?: ArtifactIdentity[];
  };
  const db = getDb();
  if (body.items) {
    db.prepare(`UPDATE sessions SET items_json = ? WHERE id = ?`).run(
      JSON.stringify(body.items),
      body.session_id,
    );
  }
  if (body.identities) {
    db.prepare(`UPDATE sessions SET identities_json = ? WHERE id = ?`).run(
      JSON.stringify(body.identities),
      body.session_id,
    );
  }
  return NextResponse.json({ ok: true });
}
