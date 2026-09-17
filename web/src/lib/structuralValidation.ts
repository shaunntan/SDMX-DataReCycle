import path from "node:path";
import fs from "node:fs";
import { spawn } from "node:child_process";

export const REPO_ROOT = path.resolve(process.cwd(), "..");
export const PROTOTYPE_DIR = path.join(REPO_ROOT, "PrototypeCodes");
export const PYTHON_BIN = path.join(PROTOTYPE_DIR, ".venv", "bin", "python3");

export type StructuralResult = { valid: boolean; errors: string[] };

/**
 * Run a PrototypeCodes script that reads one JSON object on stdin and prints
 * one JSON object on stdout. Resolves to null when the pipeline venv is
 * missing, the script fails, or it times out, so callers can degrade.
 */
export function runPythonJson<T>(
  script: string,
  payload: unknown,
  timeoutMs = 180_000,
): Promise<T | null> {
  return new Promise((resolve) => {
    if (!fs.existsSync(PYTHON_BIN)) {
      resolve(null);
      return;
    }
    const child = spawn(PYTHON_BIN, [script], { cwd: PROTOTYPE_DIR });
    let stdout = "";
    let settled = false;
    const finish = (value: T | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      resolve(value);
    };
    const timer = setTimeout(() => {
      child.kill();
      finish(null);
    }, timeoutMs);
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", () => {});
    child.on("error", () => finish(null));
    child.on("close", (code) => {
      if (code !== 0) {
        finish(null);
        return;
      }
      try {
        finish(JSON.parse(stdout) as T);
      } catch {
        finish(null);
      }
    });
    child.stdin.write(JSON.stringify(payload));
    child.stdin.end();
  });
}

/**
 * Real SDMX-ML structural validity, by reusing the pipeline's own Pydantic
 * schemas via validate_export.py. Resolves to null (rather than throwing) when
 * the pipeline venv is missing or the check fails, so callers can degrade.
 */
export function runStructuralValidation(
  grouped: Record<string, unknown[]>,
): Promise<Record<string, StructuralResult> | null> {
  return new Promise((resolve) => {
    if (!fs.existsSync(PYTHON_BIN)) {
      resolve(null);
      return;
    }
    const child = spawn(PYTHON_BIN, ["validate_export.py"], { cwd: PROTOTYPE_DIR });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d));
    child.stderr.on("data", (d) => (stderr += d));
    child.on("close", (code) => {
      if (code !== 0) {
        resolve(null);
        return;
      }
      try {
        resolve(JSON.parse(stdout));
      } catch {
        resolve(null);
      }
      void stderr;
    });
    child.stdin.write(JSON.stringify(grouped));
    child.stdin.end();
  });
}
