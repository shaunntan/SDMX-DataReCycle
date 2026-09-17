import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { getDb } from "@/lib/db";

export const runtime = "nodejs";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const PROTOTYPE_DIR = path.join(REPO_ROOT, "PrototypeCodes");
const INPUTS_DIR = path.join(REPO_ROOT, "Inputs");
const JOBS_DIR = path.join(process.cwd(), "data", "jobs");
const PYTHON_BIN = path.join(PROTOTYPE_DIR, ".venv", "bin", "python3");

/**
 * Triggers the REAL report-to-SDMX pipeline (PrototypeCodes/) as a detached
 * background process, since it takes minutes (multiple Codex CLI calls per
 * artifact type), not the ~1s a synchronous API response can afford.
 *
 * MVP scope: processes only the first uploaded file, and only the 3 artifact
 * types the frontend currently models (see run_web_job.py). The frontend
 * polls GET /api/upload/status?job=<id> until the job finishes.
 */
export async function POST(req: Request) {
  const form = await req.formData();
  const files = form.getAll("files").filter((f): f is File => f instanceof File);
  if (files.length === 0) {
    return NextResponse.json({ error: "No files selected" }, { status: 400 });
  }
  if (!fs.existsSync(PYTHON_BIN)) {
    return NextResponse.json(
      { error: `Pipeline environment not set up: ${PYTHON_BIN} not found. Run "python3 -m venv .venv && .venv/bin/pip install -r requirements.txt" in PrototypeCodes/ first.` },
      { status: 503 },
    );
  }

  const jobId = `job-${Date.now()}`;
  const jobDir = path.join(JOBS_DIR, jobId);
  fs.mkdirSync(INPUTS_DIR, { recursive: true });
  fs.mkdirSync(jobDir, { recursive: true });

  // A new upload supersedes whatever was last reviewed: Metadata Review should
  // read as empty until THIS job's real response is back, not show stale data
  // from a previous session while the new one is still processing.
  getDb().prepare(`DELETE FROM active_session WHERE k = 1`).run();

  const file = files[0];
  const safeName = file.name.replace(/[^A-Za-z0-9._-]/g, "_");
  const inputFilename = `${jobId}__${safeName}`;
  const buffer = Buffer.from(await file.arrayBuffer());
  fs.writeFileSync(path.join(INPUTS_DIR, inputFilename), buffer);

  const stem = inputFilename.replace(/\.[^.]+$/, "");
  const statusFile = path.join(jobDir, "status.json");
  fs.writeFileSync(
    statusFile,
    JSON.stringify({
      file: inputFilename,
      stem,
      phase: "QUEUED",
      steps: { CONCEPT_SCHEME: "PENDING", CODELISTS: "PENDING", DSD_KEY_FAMILY: "PENDING" },
      error: null,
    }),
  );

  const logFd = fs.openSync(path.join(jobDir, "run.log"), "a");
  const child = spawn(
    PYTHON_BIN,
    ["run_web_job.py", "--file", inputFilename, "--status-file", statusFile],
    { cwd: PROTOTYPE_DIR, detached: true, stdio: ["ignore", logFd, logFd] },
  );
  child.unref();

  return NextResponse.json({ job_id: jobId, filenames: files.map((f) => f.name) });
}
