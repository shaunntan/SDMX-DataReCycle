import { NextResponse } from "next/server";
import { buildExportSuggestPayload } from "@/lib/exportSuggestPayload";
import { runPythonJson } from "@/lib/structuralValidation";

export const runtime = "nodejs";

type PromptResult = { prompt: string | null; unavailable: boolean; note?: string };

/**
 * The exact prompt /api/export/suggest would send to codex, so the user can
 * review and edit it before triggering the call (dry run: export_suggest.py
 * never calls codex here).
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { ids: number[] };
  const ids = body.ids ?? [];
  if (!ids.length) {
    return NextResponse.json({ error: "No artifacts selected" }, { status: 400 });
  }

  const payload = await buildExportSuggestPayload(ids);
  const result = await runPythonJson<PromptResult>("export_suggest.py", {
    ...payload,
    dry_run: true,
  });

  if (!result) return NextResponse.json({ prompt: null, unavailable: true });
  return NextResponse.json({
    prompt: result.prompt ?? null,
    unavailable: !!result.unavailable,
    ...(result.note ? { note: result.note } : {}),
  });
}
