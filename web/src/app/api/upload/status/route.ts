import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";
import { getDb } from "@/lib/db";
import { buildReviewItemsFromRealArtifacts } from "@/lib/realSdmxAdapter";

export const runtime = "nodejs";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const JOBS_DIR = path.join(process.cwd(), "data", "jobs");

type JobStatus = {
  file: string;
  stem: string;
  phase: "QUEUED" | "RUNNING" | "DONE" | "FAILED";
  steps: Record<string, string>;
  data_conversion?: Record<string, { status: string; error: string | null }>;
  error: string | null;
  session_id?: string;
};

function latestJobId(): string | null {
  if (!fs.existsSync(JOBS_DIR)) return null;
  const ids = fs
    .readdirSync(JOBS_DIR, { withFileTypes: true })
    .filter((entry) => entry.isDirectory() && fs.existsSync(path.join(JOBS_DIR, entry.name, "status.json")))
    .map((entry) => entry.name)
    .sort();
  return ids.length ? ids[ids.length - 1] : null;
}

export async function GET(req: Request) {
  const requestedJobId = new URL(req.url).searchParams.get("job");
  const jobId = requestedJobId ?? latestJobId();
  if (!jobId) {
    return NextResponse.json({ error: "No upload jobs yet" }, { status: 404 });
  }
  const statusFile = path.join(JOBS_DIR, jobId, "status.json");
  if (!fs.existsSync(statusFile)) {
    return NextResponse.json({ error: "Unknown job" }, { status: 404 });
  }

  const status = JSON.parse(fs.readFileSync(statusFile, "utf-8")) as JobStatus;

  if (status.phase === "DONE" && !status.session_id) {
    const { items, identities, raw } = buildReviewItemsFromRealArtifacts(REPO_ROOT, status.stem);
    const db = getDb();
    const sessionId = `sess-${Date.now()}`;
    db.prepare(
      `INSERT INTO sessions (id, created_at, filenames, items_json, identities_json, raw_json, data_conversion_json) VALUES (?, ?, ?, ?, ?, ?, ?)`,
    ).run(
      sessionId,
      new Date().toISOString(),
      JSON.stringify([status.file]),
      JSON.stringify(items),
      JSON.stringify(identities),
      JSON.stringify(raw),
      JSON.stringify(status.data_conversion ?? {}),
    );
    db.prepare(
      `INSERT INTO active_session (k, session_id) VALUES (1, ?)
       ON CONFLICT(k) DO UPDATE SET session_id = excluded.session_id`,
    ).run(sessionId);
    status.session_id = sessionId;
    fs.writeFileSync(statusFile, JSON.stringify(status));
  }

  return NextResponse.json({ job_id: jobId, ...status });
}
