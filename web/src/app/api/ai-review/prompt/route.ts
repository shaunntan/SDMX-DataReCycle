import { NextResponse } from "next/server";
import { loadAiReviewPayload } from "@/lib/aiReviewPayload";
import { runPythonJson } from "@/lib/structuralValidation";

export const runtime = "nodejs";

type PromptResult = { prompt: string | null; unavailable: boolean; note?: string };

/**
 * The exact prompt /api/ai-review would send to codex, so the user can review
 * and edit it before triggering the call (dry run: ai_review.py never calls
 * codex here).
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { saved_artifact_id: number };
  const loaded = loadAiReviewPayload(body.saved_artifact_id);
  if (!loaded) return NextResponse.json({ error: "Artifact not found" }, { status: 404 });

  const result = await runPythonJson<PromptResult>("ai_review.py", {
    ...loaded.stdin,
    dry_run: true,
  });

  if (!result) return NextResponse.json({ prompt: null, unavailable: true });
  return NextResponse.json({
    prompt: result.prompt ?? null,
    unavailable: !!result.unavailable,
    ...(result.note ? { note: result.note } : {}),
  });
}
