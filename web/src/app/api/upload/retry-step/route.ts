import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";

export const runtime = "nodejs";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const PROTOTYPE_DIR = path.join(REPO_ROOT, "PrototypeCodes");
const JOBS_DIR = path.join(process.cwd(), "data", "jobs");
const PYTHON_BIN = path.join(PROTOTYPE_DIR, ".venv", "bin", "python3");

/**
 * Retries ONE artifact-type generation with a user-edited prompt
 * (run_manual_retry.py). Single generate+validate call, no auto-retry loop.
 * On success it's promoted to canonical and the job resumes past it; on
 * failure it's just recorded as a new attempt for the user to see.
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { job_id: string; step: string; prompt: string };
  if (!body.job_id || !body.step || !body.prompt) {
    return NextResponse.json({ error: "Missing job_id, step, or prompt" }, { status: 400 });
  }
  const statusFile = path.join(JOBS_DIR, body.job_id, "status.json");
  if (!fs.existsSync(statusFile)) {
    return NextResponse.json({ error: "Unknown job" }, { status: 404 });
  }
  const status = JSON.parse(fs.readFileSync(statusFile, "utf-8"));

  const jobDir = path.join(JOBS_DIR, body.job_id);
  const logFd = fs.openSync(path.join(jobDir, "run.log"), "a");
  const child = spawn(
    PYTHON_BIN,
    ["run_manual_retry.py", "--file", status.file, "--artifact", body.step, "--status-file", statusFile],
    { cwd: PROTOTYPE_DIR, detached: true, stdio: ["pipe", logFd, logFd] },
  );
  child.stdin?.write(body.prompt);
  child.stdin?.end();
  child.unref();

  return NextResponse.json({ ok: true });
}
