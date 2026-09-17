import { NextResponse } from "next/server";
import { loadAiReviewPayload } from "@/lib/aiReviewPayload";
import { mockAiReview } from "@/lib/mockSdmx";
import { runPythonJson } from "@/lib/structuralValidation";
import type { SuggestedChange } from "@/lib/types";

export const runtime = "nodejs";

type ReviewResult = { changes: SuggestedChange[]; unavailable: boolean; note?: string };

/**
 * AI review of a saved metadata artifact, via the pipeline's codex CLI
 * (ai_review.py). If the pipeline venv or the codex CLI isn't available the
 * response falls back to placeholder suggestions and says so, rather than
 * failing, so the UI can label them as placeholders. An optional `prompt` in
 * the body (from the prompt editor) is sent verbatim instead of the template.
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { saved_artifact_id: number; prompt?: string };
  const loaded = loadAiReviewPayload(body.saved_artifact_id);
  if (!loaded) return NextResponse.json({ error: "Artifact not found" }, { status: 404 });
  const { row, items, stdin } = loaded;

  const result = await runPythonJson<ReviewResult>("ai_review.py", {
    ...stdin,
    ...(body.prompt ? { prompt_override: body.prompt } : {}),
  });

  const artifact = { ...row, items_json: undefined };
  if (!result || result.unavailable) {
    return NextResponse.json({
      artifact,
      changes: mockAiReview(row.artifact_type, row.artifact_id, items),
      ai_unavailable: true,
      ai_note: "AI review is unavailable; showing placeholder suggestions.",
    });
  }

  return NextResponse.json({
    artifact,
    changes: result.changes ?? [],
    ai_unavailable: false,
    ...(result.note ? { ai_note: result.note } : {}),
  });
}
