import { NextResponse } from "next/server";
import { buildExportSuggestPayload } from "@/lib/exportSuggestPayload";
import { runPythonJson } from "@/lib/structuralValidation";
import type { SuggestedChange } from "@/lib/types";

export const runtime = "nodejs";

type SuggestResult = { changes: SuggestedChange[]; unavailable: boolean };

/**
 * Suggested fixes for the issues found by /api/export/check: reruns the same
 * reference + structural checks, then asks Codex (export_suggest.py) to
 * propose concrete corrections. Degrades to an empty, `unavailable: true`
 * result when the pipeline venv or the codex CLI isn't available. An optional
 * `prompt` in the body (from the prompt editor) is sent verbatim instead of
 * the template.
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { ids: number[]; prompt?: string };
  const ids = body.ids ?? [];
  if (!ids.length) {
    return NextResponse.json({ error: "No artifacts selected" }, { status: 400 });
  }

  const payload = await buildExportSuggestPayload(ids);
  const result = await runPythonJson<SuggestResult>("export_suggest.py", {
    ...payload,
    ...(body.prompt ? { prompt_override: body.prompt } : {}),
  });

  if (!result) return NextResponse.json({ changes: [], unavailable: true });
  return NextResponse.json({ changes: result.changes ?? [], unavailable: !!result.unavailable });
}
