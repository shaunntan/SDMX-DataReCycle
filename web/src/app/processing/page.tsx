"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { PIPELINE_STEPS, STEP_LABELS, type PipelineStepKey } from "@/lib/pipelineSteps";

type Attempt = {
  id: number;
  source: "auto" | "manual";
  prompt: string | null;
  status: "SUCCESS" | "FAILED";
  error: string | null;
  created_at: string;
};

type JobStatus = {
  job_id: string;
  file: string;
  phase: "QUEUED" | "RUNNING" | "NEEDS_INPUT" | "DONE" | "FAILED";
  steps: Record<string, string>;
  attempts: Partial<Record<PipelineStepKey, Attempt[]>>;
  selected_attempt: Partial<Record<PipelineStepKey, number>>;
  error: string | null;
  session_id?: string;
};

function statusBadgeClass(value: string): string {
  if (value === "SUCCESS") return "ok";
  if (value === "FAILED") return "bad";
  if (value === "RUNNING") return "warn";
  return "muted";
}

function ProcessingInner() {
  const jobId = useSearchParams().get("job");
  const [status, setStatus] = useState<JobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notFound, setNotFound] = useState(false);
  const [expanded, setExpanded] = useState<PipelineStepKey | null>(null);
  const [drafts, setDrafts] = useState<Partial<Record<PipelineStepKey, string>>>({});
  const [busyStep, setBusyStep] = useState<PipelineStepKey | null>(null);

  useEffect(() => {
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;

    async function poll() {
      try {
        const url = jobId ? `/api/upload/status?job=${jobId}` : "/api/upload/status";
        const res = await fetch(url);
        const json = await res.json();
        if (cancelled) return;
        if (res.status === 404) {
          setNotFound(true);
          return;
        }
        if (!res.ok) throw new Error(json.error ?? "Job lookup failed");
        setStatus(json);
        setNotFound(false);
        timer = setTimeout(poll, 4000);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      }
    }
    poll();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [jobId]);

  async function retry(step: PipelineStepKey) {
    if (!status) return;
    const prompt = drafts[step];
    if (!prompt) return;
    setBusyStep(step);
    try {
      await fetch("/api/upload/retry-step", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: status.job_id, step, prompt }),
      });
    } finally {
      setBusyStep(null);
    }
  }

  async function selectAttempt(step: PipelineStepKey, attemptId: number) {
    if (!status) return;
    setBusyStep(step);
    try {
      await fetch("/api/upload/select-attempt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ job_id: status.job_id, step, attempt_id: attemptId }),
      });
    } finally {
      setBusyStep(null);
    }
  }

  if (notFound) {
    return (
      <>
        <h1>Processing report</h1>
        <p className="hint">No upload job found yet. Upload a report first.</p>
        <Link href="/upload">Go to Upload</Link>
      </>
    );
  }

  return (
    <>
      <h1>Processing report</h1>
      <p className="hint">
        Running the real report-to-SDMX pipeline (Concept Scheme, Codelists, DSD/Key Family,
        Dataflow) via Codex, then converting the data. You can leave and come back &mdash; this
        page always shows the most recent upload job&apos;s status.
      </p>
      {status && (
        <>
          <p className="muted">
            File: {status.file} &middot; Job status:{" "}
            <span className={statusBadgeClass(status.phase === "DONE" ? "SUCCESS" : status.phase)}>
              {status.phase}
            </span>
          </p>

          <ul className="steps">
            {PIPELINE_STEPS.map((step) => {
              const stepStatus = status.steps[step] ?? "PENDING";
              const attempts = status.attempts?.[step] ?? [];
              const selectedId = status.selected_attempt?.[step];
              const latest = attempts[attempts.length - 1];
              const isExpanded = expanded === step;

              return (
                <li key={step} className="step-row" style={{ flexDirection: "column", alignItems: "stretch" }}>
                  <div className="row" style={{ margin: 0, justifyContent: "space-between" }}>
                    <span>
                      {STEP_LABELS[step]} <span className={statusBadgeClass(stepStatus)}>{stepStatus}</span>
                    </span>
                    <button onClick={() => setExpanded(isExpanded ? null : step)}>
                      {isExpanded ? "Hide" : "Show"} prompt &amp; attempts
                    </button>
                  </div>

                  {isExpanded && (
                    <div className="box">
                      <label>
                        Prompt {latest ? `(from attempt #${latest.id}, ${latest.source})` : ""}
                        <textarea
                          rows={10}
                          value={drafts[step] ?? latest?.prompt ?? ""}
                          onChange={(e) => setDrafts((d) => ({ ...d, [step]: e.target.value }))}
                        />
                      </label>
                      <div className="row">
                        <button
                          onClick={() => retry(step)}
                          disabled={busyStep === step || stepStatus === "RUNNING" || !(drafts[step] ?? latest?.prompt)}
                          title={stepStatus === "SUCCESS" ? "Retrying will create a new candidate attempt without changing the current selection unless you pick it" : undefined}
                        >
                          {busyStep === step ? "Retrying…" : "Retry with this prompt"}
                        </button>
                      </div>

                      {attempts.length > 0 && (
                        <>
                          <p className="muted" style={{ marginTop: 12 }}>
                            Attempts ({attempts.length}):
                          </p>
                          <table>
                            <thead>
                              <tr>
                                <th>#</th>
                                <th>Source</th>
                                <th>Status</th>
                                <th>Created</th>
                                <th>Error</th>
                                <th>Action</th>
                              </tr>
                            </thead>
                            <tbody>
                              {attempts.map((a) => (
                                <tr key={a.id}>
                                  <td>{a.id}</td>
                                  <td>{a.source}</td>
                                  <td className={statusBadgeClass(a.status)}>{a.status}</td>
                                  <td className="muted">{new Date(a.created_at).toLocaleTimeString()}</td>
                                  <td className="muted">{a.error ?? "—"}</td>
                                  <td>
                                    {a.status === "SUCCESS" ? (
                                      selectedId === a.id ? (
                                        <span className="ok">in use</span>
                                      ) : (
                                        <button disabled={busyStep === step} onClick={() => selectAttempt(step, a.id)}>
                                          Use this response
                                        </button>
                                      )
                                    ) : (
                                      <span className="muted">—</span>
                                    )}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </>
                      )}
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          {status.phase === "NEEDS_INPUT" && (
            <p className="bad">
              Paused: {status.error} &mdash; edit the prompt above and retry, or pick a different
              stored attempt if one succeeded.
            </p>
          )}
          {status.phase === "DONE" && (
            <p>
              <Link className="primary" href="/review">
                Metadata is ready — go to Review
              </Link>
            </p>
          )}
        </>
      )}
      {error && <p className="bad">{error}</p>}
    </>
  );
}

export default function ProcessingPage() {
  return (
    <Suspense fallback={<p>Loading…</p>}>
      <ProcessingInner />
    </Suspense>
  );
}
