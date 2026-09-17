import { NextResponse } from "next/server";
import { getDb } from "@/lib/db";
import { applyChangesToArtifact } from "@/lib/applyChanges";
import type { SuggestedChange } from "@/lib/types";

export const runtime = "nodejs";

/** Persist accepted AI-suggested changes onto a saved artifact. */
export async function POST(req: Request) {
  const body = (await req.json()) as {
    saved_artifact_id: number;
    changes: SuggestedChange[];
  };
  const applied = applyChangesToArtifact(getDb(), body.saved_artifact_id, body.changes);
  if (applied === null) return NextResponse.json({ error: "Artifact not found" }, { status: 404 });

  return NextResponse.json({ ok: true, applied });
}
