import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { reconstructArtifact } from "@/lib/reconstructArtifact";
import type { RawArtifactEnvelopes } from "@/lib/realSdmxAdapter";
import type { ArtifactIdentity, ReviewItem } from "@/lib/types";

export const runtime = "nodejs";

/** List saved artifacts (grouped listing is done client-side). */
export async function GET() {
  const rows = getDb()
    .prepare(
      `SELECT id, artifact_type, artifact_id, version, name, agency_id, saved_at
       FROM saved_artifacts ORDER BY artifact_type, artifact_id, id DESC`,
    )
    .all();
  return NextResponse.json({ artifacts: rows });
}

/**
 * Save one fully-accepted metadata set from the active review session.
 *
 * Per SDMX: Agency ID + Artifact ID + Version identify a maintainable
 * artifact, and are governance decisions a human curator must confirm --
 * an AI extraction can only guess (hence placeholders like
 * "SYNTHETIC_LABOUR_OBSERVATORY" / "1.0-draft"). Name is required too but
 * lower-risk. The client must supply a confirmed ArtifactIdentity for every
 * distinct artifact_id present in `items`; Artifact ID itself isn't
 * renameable here (it's the grouping key items already reference).
 *
 * Also reconstructs a full SDMX-schema-shaped object per artifact (see
 * reconstructArtifact.ts) and stores it as structured_json, which the export
 * consistency check (/api/export/check) validates against the pipeline's
 * real Pydantic schemas.
 */
export async function POST(req: Request) {
  const body = (await req.json()) as {
    session_id: string;
    artifact_type: string;
    items: ReviewItem[];
    identities: ArtifactIdentity[];
  };
  const { session_id, artifact_type, items, identities } = body;
  if (!items.length) {
    return NextResponse.json({ error: "Nothing to save" }, { status: 400 });
  }
  if (items.some((i) => i.status === "pending")) {
    return NextResponse.json({ error: "All items must be accepted first" }, { status: 400 });
  }

  const byArtifact = new Map<string, ReviewItem[]>();
  for (const it of items) {
    if (!byArtifact.has(it.artifact_id)) byArtifact.set(it.artifact_id, []);
    byArtifact.get(it.artifact_id)!.push(it);
  }

  const identityByArtifact = new Map((identities ?? []).map((i) => [i.artifact_id, i]));
  const missing: string[] = [];
  for (const artifactId of byArtifact.keys()) {
    const identity = identityByArtifact.get(artifactId);
    if (!identity || !identity.agency_id.trim() || !identity.version.trim() || !identity.name.trim()) {
      missing.push(artifactId);
    }
  }
  if (missing.length) {
    return NextResponse.json(
      { error: `Confirm Agency ID, Version, and Name before saving: ${missing.join(", ")}` },
      { status: 400 },
    );
  }

  const db = getDb();
  const sessionRow = db
    .prepare(`SELECT raw_json FROM sessions WHERE id = ?`)
    .get(session_id) as { raw_json: string } | undefined;
  const raw = JSON.parse(sessionRow?.raw_json || "{}") as RawArtifactEnvelopes;

  const saved: Array<{ artifact_id: string; version: string }> = [];
  const insert = db.prepare(
    `INSERT INTO saved_artifacts (artifact_type, artifact_id, version, name, agency_id, saved_at, source_session, items_json, structured_json)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)`,
  );
  const tx = db.transaction(() => {
    for (const [artifactId, group] of byArtifact) {
      const identity = identityByArtifact.get(artifactId)!;
      const structured = reconstructArtifact(
        raw,
        artifact_type as ArtifactIdentity["artifact_type"],
        artifactId,
        items,
        identity,
      );
      insert.run(
        artifact_type,
        artifactId,
        identity.version,
        identity.name,
        identity.agency_id,
        new Date().toISOString(),
        session_id,
        JSON.stringify(group),
        JSON.stringify(structured ?? {}),
      );
      saved.push({ artifact_id: artifactId, version: identity.version });
    }
  });
  tx();

  return NextResponse.json({ ok: true, saved });
}
