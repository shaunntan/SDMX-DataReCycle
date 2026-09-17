import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";

export const runtime = "nodejs";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const DATA_CONVERSIONS_ROOT = path.join(REPO_ROOT, "Data Conversions");

/**
 * Serves the Codex-generated conversion script + Parquet preview for one
 * DSD, written by PrototypeCodes/run_data_conversion.py to
 * "<repoRoot>/Data Conversions/<stem>__<dsdId>/".
 */
export async function GET(req: Request) {
  const { searchParams } = new URL(req.url);
  const stem = searchParams.get("stem");
  const dsdId = searchParams.get("dsd_id");
  if (!stem || !dsdId) {
    return NextResponse.json({ error: "Missing stem or dsd_id" }, { status: 400 });
  }

  const dir = path.join(DATA_CONVERSIONS_ROOT, `${stem}__${dsdId}`);
  if (!fs.existsSync(dir)) {
    return NextResponse.json({ error: "No conversion found for this DSD yet" }, { status: 404 });
  }

  const scriptPath = path.join(dir, "convert.py");
  const previewPath = path.join(dir, "preview.json");
  const script = fs.existsSync(scriptPath) ? fs.readFileSync(scriptPath, "utf-8") : null;
  const preview = fs.existsSync(previewPath)
    ? JSON.parse(fs.readFileSync(previewPath, "utf-8"))
    : null;
  const hasParquet = fs.existsSync(path.join(dir, "output.parquet"));

  return NextResponse.json({ script, preview, has_parquet: hasParquet });
}
