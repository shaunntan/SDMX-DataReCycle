"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { ARTIFACT_LABEL, type ArtifactType, type SuggestedChange } from "@/lib/types";

type SavedArtifact = {
  id: number;
  artifact_type: ArtifactType;
  artifact_id: string;
  version: string;
  saved_at: string;
};

const ORDER: ArtifactType[] = ["dsd", "codelist", "conceptscheme", "dataflow"];

type CheckResult = {
  reference_issues: string[];
  structural: Record<ArtifactType, { valid: boolean; errors: string[] }> | null;
  structural_unavailable: boolean;
};

type Decision = "accept" | "reject" | null;

export default function ExportPage() {
  const [artifacts, setArtifacts] = useState<SavedArtifact[]>([]);
  const [selection, setSelection] = useState<Record<string, number | "">>({});
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);
  const [checkResult, setCheckResult] = useState<CheckResult | null>(null);
  const [suggesting, setSuggesting] = useState(false);
  const [suggestions, setSuggestions] = useState<SuggestedChange[] | null>(null);
  const [suggestUnavailable, setSuggestUnavailable] = useState(false);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [prompt, setPrompt] = useState<string | null>(null);
  const [promptNote, setPromptNote] = useState<string | null>(null);
  const [promptShown, setPromptShown] = useState(false);
  const [promptLoading, setPromptLoading] = useState(false);

  useEffect(() => {
    fetch("/api/metadata")
      .then((r) => r.json())
      .then((j) => setArtifacts(j.artifacts ?? []))
      .finally(() => setLoading(false));
  }, []);

  const byType = useMemo(() => {
    const m = new Map<ArtifactType, SavedArtifact[]>();
    for (const t of ORDER) m.set(t, []);
    for (const a of artifacts) m.get(a.artifact_type)?.push(a);
    return m;
  }, [artifacts]);

  const chosenIds = Object.values(selection).filter((v): v is number => typeof v === "number");

  async function checkConsistency() {
    setChecking(true);
    setCheckResult(null);
    try {
      const res = await fetch("/api/export/check", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: chosenIds }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Check failed");
      setCheckResult(json);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setChecking(false);
    }
  }

  async function loadPrompt() {
    if (chosenIds.length === 0) return;
    setPromptLoading(true);
    setPromptShown(true);
    setPrompt(null);
    setPromptNote(null);
    setMessage(null);
    try {
      const res = await fetch("/api/export/suggest/prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: chosenIds }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Prompt build failed");
      setPrompt(typeof json.prompt === "string" ? json.prompt : null);
      setPromptNote(json.note ?? null);
    } catch (e) {
      setPromptNote(e instanceof Error ? e.message : String(e));
    } finally {
      setPromptLoading(false);
    }
  }

  async function getSuggestions() {
    setSuggesting(true);
    setMessage(null);
    setSuggestions(null);
    setSuggestUnavailable(false);
    setDecisions({});
    try {
      const res = await fetch("/api/export/suggest", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          ids: chosenIds,
          ...(prompt && prompt.trim() ? { prompt } : {}),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Suggest failed");
      setSuggestions(json.changes ?? []);
      setSuggestUnavailable(Boolean(json.unavailable));
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setSuggesting(false);
    }
  }

  async function applySuggestions() {
    if (!suggestions) return;
    const selectedArtifacts = artifacts.filter((a) => chosenIds.includes(a.id));
    const payload = suggestions
      .filter((c) => c.item_id && decisions[c.change_id] === "accept")
      .map((c) => {
        const saved = selectedArtifacts.find(
          (a) => a.artifact_type === c.artifact_type && a.artifact_id === c.artifact_id,
        );
        return saved ? { ...c, saved_artifact_id: saved.id } : null;
      })
      .filter((c): c is SuggestedChange & { saved_artifact_id: number } => c !== null);
    if (payload.length === 0) return;
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/export/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ changes: payload }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Apply failed");
      setMessage(`Applied ${json.applied} change(s). Re-run "Check consistency" to see the effect.`);
      setSuggestions(null);
      setSuggestUnavailable(false);
      setDecisions({});
      setCheckResult(null);
      setPromptShown(false);
      setPrompt(null);
      setPromptNote(null);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function doExport() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/export", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: chosenIds }),
      });
      if (!res.ok) throw new Error(await res.text());
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "sdmx_export.zip.txt";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
      setMessage(`Exported ${chosenIds.length} artifact(s).`);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const acceptedCount = suggestions
    ? suggestions.filter((c) => c.item_id && decisions[c.change_id] === "accept").length
    : 0;

  if (loading) return <p>Loading…</p>;

  return (
    <>
      <h1>Export</h1>
      <p className="hint">Pick a saved version per metadata type, then export the selection.</p>
      <div className="stubnote">
        STUB: the export returns a plain-text stand-in for the real SDMX-ML zip archive.
      </div>

      {artifacts.length === 0 ? (
        <p>
          Nothing saved yet. <Link href="/upload">Upload</Link> and save metadata first.
        </p>
      ) : (
        <table>
          <thead>
            <tr>
              <th style={{ width: "25%" }}>Metadata type</th>
              <th style={{ width: "50%" }}>Available artifacts</th>
              <th style={{ width: "25%" }}>Saved at</th>
            </tr>
          </thead>
          <tbody>
            {ORDER.map((t) => {
              const list = byType.get(t) ?? [];
              const sel = selection[t];
              const picked = list.find((a) => a.id === sel);
              return (
                <tr key={t}>
                  <td>{ARTIFACT_LABEL[t]}</td>
                  <td>
                    <select
                      value={sel ?? ""}
                      disabled={list.length === 0}
                      onChange={(e) =>
                        setSelection((s) => ({
                          ...s,
                          [t]: e.target.value === "" ? "" : Number(e.target.value),
                        }))
                      }
                    >
                      <option value="">
                        {list.length === 0 ? "(none saved)" : "-- not included --"}
                      </option>
                      {list.map((a) => (
                        <option key={a.id} value={a.id}>
                          {a.artifact_id} v{a.version}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="muted">{picked ? new Date(picked.saved_at).toLocaleString() : "—"}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}

      <div className="row">
        <button onClick={checkConsistency} disabled={checking || chosenIds.length === 0}>
          {checking ? "Checking…" : "Check consistency"}
        </button>
        <button onClick={loadPrompt} disabled={promptLoading || chosenIds.length === 0}>
          {promptLoading ? "Building prompt…" : "Get suggested fixes"}
        </button>
        <button className="primary" onClick={doExport} disabled={busy || chosenIds.length === 0}>
          {busy ? "Zipping…" : "Export"}
        </button>
        <span className="muted">{chosenIds.length} selected</span>
      </div>
      {message && <p className="muted">{message}</p>}

      {checkResult && <ConsistencyReport result={checkResult} />}

      {promptShown && (
        <div className="box">
          <strong>Codex prompt</strong>{" "}
          <span className="muted">(edit before sending; you can retry with a different prompt)</span>
          {promptLoading ? (
            <p className="muted">Loading prompt…</p>
          ) : prompt === null ? (
            <p className="muted">{promptNote ?? "No prompt available."}</p>
          ) : (
            <>
              <textarea
                rows={16}
                value={prompt}
                onChange={(e) => setPrompt(e.target.value)}
                style={{
                  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
                  fontSize: 12,
                  marginTop: 8,
                }}
              />
              <div className="row">
                <button
                  className="primary"
                  onClick={getSuggestions}
                  disabled={suggesting || chosenIds.length === 0}
                >
                  {suggesting ? "Asking Codex…" : suggestions ? "Retry with edited prompt" : "Send to Codex"}
                </button>
              </div>
            </>
          )}
        </div>
      )}

      {suggestions && (
        <div className="box">
          <strong>Suggested fixes</strong>
          {suggestUnavailable ? (
            <p className="muted">Codex CLI unavailable — no suggested fixes available.</p>
          ) : suggestions.length === 0 ? (
            <p className="muted">No suggested fixes.</p>
          ) : (
            <>
              <table>
                <thead>
                  <tr>
                    <th>Artifact</th>
                    <th>Field</th>
                    <th>Current</th>
                    <th>Suggested</th>
                    <th>Rationale</th>
                    <th style={{ width: 150 }}>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {suggestions.map((c) => {
                    const d = decisions[c.change_id] ?? null;
                    return (
                      <tr key={c.change_id}>
                        <td>
                          {ARTIFACT_LABEL[c.artifact_type]} · {c.artifact_id}
                          {c.item_id ? ` · ${c.item_id}` : ""}
                        </td>
                        <td>{c.field}</td>
                        <td className="muted">{c.current_value || "—"}</td>
                        <td>{c.suggested_value || "—"}</td>
                        <td className="muted">{c.rationale}</td>
                        <td>
                          {c.item_id ? (
                            <>
                              <button
                                className={`tick ${d === "accept" ? "on" : ""}`}
                                onClick={() =>
                                  setDecisions((s) => ({ ...s, [c.change_id]: "accept" }))
                                }
                              >
                                ✓
                              </button>{" "}
                              <button
                                className={`cross ${d === "reject" ? "on" : ""}`}
                                onClick={() =>
                                  setDecisions((s) => ({ ...s, [c.change_id]: "reject" }))
                                }
                              >
                                ✕
                              </button>
                            </>
                          ) : (
                            <span className="muted">manual confirmation needed</span>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="row">
                <button
                  className="primary"
                  onClick={applySuggestions}
                  disabled={busy || acceptedCount === 0}
                >
                  Apply selected
                </button>
                <span className="muted">{acceptedCount} marked for acceptance</span>
              </div>
            </>
          )}
        </div>
      )}
    </>
  );
}

function ConsistencyReport({ result }: { result: CheckResult }) {
  const structuralIssues = result.structural
    ? Object.entries(result.structural).flatMap(([type, r]) =>
        r.valid ? [] : r.errors.map((e) => `${ARTIFACT_LABEL[type as ArtifactType]}: ${e}`),
      )
    : [];
  const allIssues = [...result.reference_issues, ...structuralIssues];

  return (
    <div className="box">
      <strong>Consistency check</strong>{" "}
      <span className="muted">(informational — export is not blocked by these findings)</span>
      {result.structural_unavailable && (
        <p className="muted">
          SDMX-ML structural validation unavailable (pipeline environment not set up); only
          cross-reference/identity checks ran.
        </p>
      )}
      {allIssues.length === 0 ? (
        <p className="ok">No issues found.</p>
      ) : (
        <ul>
          {allIssues.map((issue, i) => (
            <li key={i} className="bad">
              {issue}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
