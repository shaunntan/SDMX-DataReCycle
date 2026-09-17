"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import {
  ARTIFACT_LABEL,
  effectiveValue,
  type ArtifactType,
  type ReviewItem,
  type SuggestedChange,
} from "@/lib/types";

type SavedArtifact = {
  id: number;
  artifact_type: ArtifactType;
  artifact_id: string;
  version: string;
  saved_at: string;
};

type Decision = "accept" | "reject" | null;

const TYPES = Object.keys(ARTIFACT_LABEL) as ArtifactType[];

export default function ReviewMetadataPage() {
  const [artifacts, setArtifacts] = useState<SavedArtifact[]>([]);
  const [selectedType, setSelectedType] = useState<ArtifactType | "">("");
  const [selectedId, setSelectedId] = useState<number | "">("");
  const [storedItems, setStoredItems] = useState<ReviewItem[] | null>(null);
  const [storedLoading, setStoredLoading] = useState(false);
  const [aiUnavailable, setAiUnavailable] = useState(false);
  const [aiNote, setAiNote] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [changes, setChanges] = useState<SuggestedChange[] | null>(null);
  const [decisions, setDecisions] = useState<Record<string, Decision>>({});
  const [message, setMessage] = useState<string | null>(null);
  const [prompt, setPrompt] = useState<string | null>(null);
  const [promptNote, setPromptNote] = useState<string | null>(null);
  const [promptLoading, setPromptLoading] = useState(false);

  useEffect(() => {
    fetch("/api/metadata")
      .then((r) => r.json())
      .then((j) => setArtifacts(j.artifacts ?? []))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (selectedId === "") {
      setStoredItems(null);
      return;
    }
    let cancelled = false;
    setStoredLoading(true);
    fetch(`/api/metadata/${selectedId}`)
      .then((r) => r.json())
      .then((j) => {
        if (!cancelled) setStoredItems(j.items ?? []);
      })
      .finally(() => {
        if (!cancelled) setStoredLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  useEffect(() => {
    if (selectedId === "") {
      setPrompt(null);
      setPromptNote(null);
      return;
    }
    let cancelled = false;
    setPromptLoading(true);
    setPrompt(null);
    setPromptNote(null);
    fetch("/api/ai-review/prompt", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ saved_artifact_id: selectedId }),
    })
      .then((r) => r.json())
      .then((j) => {
        if (cancelled) return;
        if (j.error) {
          setPromptNote(j.error);
          return;
        }
        setPrompt(typeof j.prompt === "string" ? j.prompt : null);
        setPromptNote(j.note ?? null);
      })
      .catch((e) => {
        if (!cancelled) setPromptNote(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setPromptLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedId]);

  async function runReview() {
    if (selectedId === "") return;
    setBusy(true);
    setMessage(null);
    setChanges(null);
    setDecisions({});
    setAiUnavailable(false);
    setAiNote(null);
    try {
      const res = await fetch("/api/ai-review", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          saved_artifact_id: selectedId,
          ...(prompt && prompt.trim() ? { prompt } : {}),
        }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Review failed");
      setChanges(json.changes ?? []);
      setAiUnavailable(Boolean(json.ai_unavailable));
      setAiNote(json.ai_note ?? null);
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function applyAccepted() {
    if (!changes || selectedId === "") return;
    const accepted = changes.filter((c) => decisions[c.change_id] === "accept");
    setBusy(true);
    setMessage(null);
    try {
      const res = await fetch("/api/ai-review/apply", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ saved_artifact_id: selectedId, changes: accepted }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Apply failed");
      setMessage(`Applied ${json.applied} change(s) to the database.`);
      setChanges(null);
      setDecisions({});
    } catch (e) {
      setMessage(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const visibleArtifacts =
    selectedType === "" ? [] : artifacts.filter((a) => a.artifact_type === selectedType);

  const acceptedCount = changes
    ? changes.filter((c) => decisions[c.change_id] === "accept").length
    : 0;

  if (loading) return <p>Loading…</p>;

  return (
    <>
      <h1>Review Metadata</h1>
      <p className="hint">Run an automated review over a metadata set already stored in the database.</p>
      {artifacts.length === 0 ? (
        <p>
          No metadata in the database yet. <Link href="/upload">Upload</Link> and save some first.
        </p>
      ) : (
        <div className="row">
          <select
            value={selectedType}
            onChange={(e) => {
              setSelectedType(e.target.value === "" ? "" : (e.target.value as ArtifactType));
              setSelectedId("");
              setChanges(null);
            }}
            style={{ maxWidth: 220 }}
          >
            <option value="">-- select a metadata type --</option>
            {TYPES.map((t) => (
              <option key={t} value={t}>
                {ARTIFACT_LABEL[t]}
              </option>
            ))}
          </select>
          <select
            value={selectedId}
            disabled={selectedType === ""}
            onChange={(e) => {
              setSelectedId(e.target.value === "" ? "" : Number(e.target.value));
              setChanges(null);
            }}
            style={{ maxWidth: 420 }}
          >
            <option value="">-- select a metadata set --</option>
            {visibleArtifacts.map((a) => (
              <option key={a.id} value={a.id}>
                {a.artifact_id} v{a.version}
              </option>
            ))}
          </select>
          <button
            className="primary"
            onClick={runReview}
            disabled={busy || selectedId === "" || promptLoading || prompt === null}
          >
            {busy ? "Reviewing…" : changes ? "Retry with edited prompt" : "Review with Codex"}
          </button>
        </div>
      )}

      {message && <p className="muted">{message}</p>}

      {selectedId !== "" && (
        <div className="box">
          <strong>Codex prompt</strong>{" "}
          <span className="muted">(edit before sending; you can retry with a different prompt)</span>
          {promptLoading ? (
            <p className="muted">Loading prompt…</p>
          ) : prompt === null ? (
            <p className="muted">{promptNote ?? "No prompt available for this metadata set."}</p>
          ) : (
            <textarea
              rows={16}
              value={prompt}
              onChange={(e) => setPrompt(e.target.value)}
              style={{ fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: 12, marginTop: 8 }}
            />
          )}
        </div>
      )}

      {selectedId !== "" && (
        <div className="box">
          <strong>Currently stored records</strong>
          {storedLoading ? (
            <p className="muted">Loading…</p>
          ) : !storedItems || storedItems.length === 0 ? (
            <p className="muted">No stored records for this metadata set.</p>
          ) : (
            <table>
              <thead>
                <tr>
                  <th>Item</th>
                  <th>Field</th>
                  <th>Current</th>
                  <th>Stored value</th>
                  <th style={{ width: 100 }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {storedItems.map((it) => (
                  <tr key={it.review_id}>
                    <td>{it.item_id}</td>
                    <td>{it.field}</td>
                    <td className="muted">{it.current_value || "—"}</td>
                    <td>{effectiveValue(it) || "—"}</td>
                    <td>
                      <span className={`badge ${it.status}`}>{it.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {changes && (
        <div className="box">
          <h2 style={{ marginTop: 0 }}>Suggested changes</h2>
          {aiUnavailable && (
            <p className="muted">Codex CLI unavailable — showing placeholder suggestions.</p>
          )}
          {!aiUnavailable && aiNote ? (
            <p className="muted">{aiNote}</p>
          ) : changes.length === 0 ? (
            <p className="muted">No issues found.</p>
          ) : (
            <>
              <table>
                <thead>
                  <tr>
                    <th>Item</th>
                    <th>Field</th>
                    <th>Current</th>
                    <th>Suggested</th>
                    <th>Rationale</th>
                    <th style={{ width: 110 }}>Decision</th>
                  </tr>
                </thead>
                <tbody>
                  {changes.map((c) => {
                    const d = decisions[c.change_id] ?? null;
                    return (
                      <tr key={c.change_id}>
                        <td>{c.item_id}</td>
                        <td>{c.field}</td>
                        <td className="muted">{c.current_value || "—"}</td>
                        <td>{c.suggested_value || "—"}</td>
                        <td className="muted">{c.rationale}</td>
                        <td>
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
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              <div className="row">
                <button className="primary" onClick={applyAccepted} disabled={busy || acceptedCount === 0}>
                  Accept selected changes
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
