import { NextResponse } from "next/server";
import fs from "node:fs";
import path from "node:path";
import { spawn } from "node:child_process";
import { STEP_ARTIFACT_FOLDER, type PipelineStepKey } from "@/lib/pipelineSteps";

export const runtime = "nodejs";

const REPO_ROOT = path.resolve(process.cwd(), "..");
const PROTOTYPE_DIR = path.join(REPO_ROOT, "PrototypeCodes");
const ARTIFACT_ROOT = path.join(REPO_ROOT, "Artifact JSON");
const JOBS_DIR = path.join(process.cwd(), "data", "jobs");
const PYTHON_BIN = path.join(PROTOTYPE_DIR, ".venv", "bin", "python3");

/**
 * Promotes an already-computed attempt (the original auto attempt, or an
 * earlier/later manual retry) to be the canonical result for that step --
 * no Codex call needed, since the attempt was already validated when it was
 * produced. Resumes the job afterward in case this unblocks later steps.
 */
export async function POST(req: Request) {
  const body = (await req.json()) as { job_id: string; step: PipelineStepKey; attempt_id: number };
  const jobDir = path.join(JOBS_DIR, body.job_id);
  const statusFile = path.join(jobDir, "status.json");
  if (!fs.existsSync(statusFile)) {
    return NextResponse.json({ error: "Unknown job" }, { status: 404 });
  }
  const status = JSON.parse(fs.readFileSync(statusFile, "utf-8"));
  const attemptFile = path.join(jobDir, "attempts", `${body.step}_${body.attempt_id}.json`);
  if (!fs.existsSync(attemptFile)) {
    return NextResponse.json({ error: "Unknown attempt" }, { status: 404 });
  }

  const canonicalDir = path.join(ARTIFACT_ROOT, STEP_ARTIFACT_FOLDER[body.step]);
  fs.mkdirSync(canonicalDir, { recursive: true });
  fs.copyFileSync(attemptFile, path.join(canonicalDir, `${status.stem}.json`));

  status.steps[body.step] = "SUCCESS";
  status.selected_attempt = status.selected_attempt ?? {};
  status.selected_attempt[body.step] = body.attempt_id;
  fs.writeFileSync(statusFile, JSON.stringify(status));

  const logFd = fs.openSync(path.join(jobDir, "run.log"), "a");
  const child = spawn(
    PYTHON_BIN,
    ["run_web_job.py", "--file", status.file, "--status-file", statusFile, "--resume"],
    { cwd: PROTOTYPE_DIR, detached: true, stdio: ["ignore", logFd, logFd] },
  );
  child.unref();

  return NextResponse.json({ ok: true });
}
