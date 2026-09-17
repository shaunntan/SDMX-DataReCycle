import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import type { ReviewItem } from "@/lib/types";

export const runtime = "nodejs";

type Row = {
  id: number;
  artifact_type: string;
  artifact_id: string;
  version: string;
  name: string;
  agency_id: string;
  saved_at: string;
  items_json: string;
};

/** Read one saved artifact, including its stored review items. */
export async function GET(_req: Request, ctx: { params: Promise<{ id: string }> }) {
  const { id } = await ctx.params;
  const row = getDb()
    .prepare(
      `SELECT id, artifact_type, artifact_id, version, name, agency_id, saved_at, items_json
       FROM saved_artifacts WHERE id = ?`,
    )
    .get(Number(id)) as Row | undefined;
  if (!row) return NextResponse.json({ error: "Not found" }, { status: 404 });

  let items: ReviewItem[] = [];
  try {
    items = JSON.parse(row.items_json || "[]") as ReviewItem[];
  } catch {
    items = [];
  }

  return NextResponse.json({
    id: row.id,
    artifact_type: row.artifact_type,
    artifact_id: row.artifact_id,
    version: row.version,
    name: row.name,
    agency_id: row.agency_id,
    saved_at: row.saved_at,
    items,
  });
}
