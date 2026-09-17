"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import { ARTIFACT_LABEL, type ArtifactIdentity, type ArtifactType, type ReviewItem } from "@/lib/types";

const ORDER: ArtifactType[] = ["dsd", "codelist", "conceptscheme", "dataflow"];

function blankIdentity(artifact_type: ArtifactType, artifact_id: string): ArtifactIdentity {
  return { artifact_type, artifact_id, name: "", agency_id: "", version: "" };
}

export default function ReviewPage() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [filenames, setFilenames] = useState<string[]>([]);
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [identities, setIdentities] = useState<ArtifactIdentity[]>([]);
  const [selected, setSelected] = useState<ArtifactType>("dsd");
  const [loading, setLoading] = useState(true);
  const [savedTypes, setSavedTypes] = useState<ArtifactType[]>([]);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    fetch("/api/session")
      .then((r) => r.json())
      .then((j) => {
        if (j.session) {
          setSessionId(j.session.id);
          setFilenames(j.session.filenames ?? []);
          setItems(j.session.items);
          setIdentities(j.session.identities ?? []);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const persist = useCallback(
    (next: ReviewItem[]) => {
      setItems(next);
      if (!sessionId) return;
      void fetch("/api/session", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, items: next }),
      });
    },
    [sessionId],
  );

  const persistIdentities = useCallback(
    (next: ArtifactIdentity[]) => {
      setIdentities(next);
      if (!sessionId) return;
      void fetch("/api/session", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, identities: next }),
      });
    },
    [sessionId],
  );

  function updateIdentity(artifactId: string, patch: Partial<ArtifactIdentity>) {
    const existing = identities.find((i) => i.artifact_id === artifactId);
    const base = existing ?? blankIdentity(selected, artifactId);
    const next = { ...base, ...patch };
    persistIdentities([...identities.filter((i) => i.artifact_id !== artifactId), next]);
  }

  const setsByType = useMemo(() => {
    const m = new Map<ArtifactType, ReviewItem[]>();
    for (const t of ORDER) m.set(t, []);
    for (const it of items) m.get(it.artifact_type)?.push(it);
    return m;
  }, [items]);

  const current = setsByType.get(selected) ?? [];
  const complete = (t: ArtifactType) => {
    const list = setsByType.get(t) ?? [];
    return list.length > 0 && list.every((i) => i.status !== "pending");
  };

  const currentArtifactIds = useMemo(
    () => Array.from(new Set(current.map((i) => i.artifact_id))),
    [current],
  );
  const identityFor = useCallback(
    (artifactId: string) =>
      identities.find((i) => i.artifact_id === artifactId) ?? blankIdentity(selected, artifactId),
    [identities, selected],
  );
  const identitiesReady = currentArtifactIds.every((id) => {
    const idn = identityFor(id);
    return idn.agency_id.trim() && idn.version.trim() && idn.name.trim();
  });

  function accept(reviewId: string, value: string) {
    persist(
      items.map((i) => {
        if (i.review_id !== reviewId) return i;
        const changed = value !== (i.suggested_value ?? "");
        return changed
          ? { ...i, status: "edited" as const, edited_value: value }
          : { ...i, status: "accepted" as const, edited_value: null };
      }),
    );
  }

  function reset(reviewId: string) {
    persist(
      items.map((i) =>
        i.review_id === reviewId ? { ...i, status: "pending" as const, edited_value: null } : i,
      ),
    );
  }

  function acceptAllInSet() {
    persist(
      items.map((i) =>
        i.artifact_type === selected && i.status === "pending"
          ? { ...i, status: "accepted" as const }
          : i,
      ),
    );
  }

  async function saveMetadata() {
    if (!sessionId) return;
    setMessage(null);
    const res = await fetch("/api/metadata", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        session_id: sessionId,
        artifact_type: selected,
        items: current,
        identities: currentArtifactIds.map(identityFor),
      }),
    });
    const json = await res.json();
    if (!res.ok) {
      setMessage(json.error ?? "Save failed");
      return;
    }
    setSavedTypes((s) => (s.includes(selected) ? s : [...s, selected]));
    setMessage(
      `Saved ${ARTIFACT_LABEL[selected]}: ` +
        json.saved.map((s: { artifact_id: string; version: string }) => `${s.artifact_id} v${s.version}`).join(", "),
    );
  }

  if (loading) return <p>Loading…</p>;
  if (!sessionId)
    return (
      <>
        <h1>Metadata Review</h1>
        <p>
          No active review session. <Link href="/upload">Upload files</Link> first.
        </p>
      </>
    );

  return (
    <>
      <h1>Metadata Review</h1>
      <p className="hint">
        Processing: <strong>{filenames.length ? filenames.join(", ") : "(unknown file)"}</strong>
      </p>
      <p className="hint">
        Review each suggested value, edit if needed, then accept. Confirm the Agency ID, Version,
        and Name for each artifact, then save a set once every row is accepted.
      </p>

      <div className="layout">
        <aside className="sidebar">
          {ORDER.map((t) => (
            <button
              key={t}
              className={t === selected ? "active" : ""}
              onClick={() => {
                setSelected(t);
                setMessage(null);
              }}
            >
              <span>{ARTIFACT_LABEL[t]}</span>
              <span className={complete(t) ? "ok" : "bad"}>{complete(t) ? "✓" : "✕"}</span>
            </button>
          ))}
        </aside>

        <section className="content">
          <div className="row">
            <strong>{ARTIFACT_LABEL[selected]}</strong>
            <span className="muted">
              {current.filter((i) => i.status !== "pending").length} / {current.length} accepted
            </span>
            <button onClick={acceptAllInSet}>Accept all remaining</button>
            <button
              className="primary"
              onClick={saveMetadata}
              disabled={!complete(selected) || !identitiesReady}
              title={!identitiesReady ? "Confirm Agency ID, Version, and Name for every artifact below first" : undefined}
            >
              Save metadata
            </button>
            {savedTypes.includes(selected) && <span className="ok">saved</span>}
          </div>
          {message && <p className="muted">{message}</p>}

          {currentArtifactIds.map((artifactId) => (
            <IdentityBox
              key={artifactId}
              identity={identityFor(artifactId)}
              onChange={(patch) => updateIdentity(artifactId, patch)}
            />
          ))}

          <ReviewTable items={current} onAccept={accept} onReset={reset} />
        </section>
      </div>
    </>
  );
}

function IdentityBox({
  identity,
  onChange,
}: {
  identity: ArtifactIdentity;
  onChange: (patch: Partial<ArtifactIdentity>) => void;
}) {
  return (
    <div className="box">
      <div className="row" style={{ marginTop: 0 }}>
        <strong>{identity.artifact_id}</strong>
        <span className="muted">
          Agency ID, Version, and Name are governance fields SDMX requires a curator to confirm
          before saving — the AI can only guess them.
        </span>
      </div>
      <div className="identity-fields">
        <label>
          Agency ID
          <input
            type="text"
            value={identity.agency_id}
            placeholder="e.g. MY_AGENCY"
            onChange={(e) => onChange({ agency_id: e.target.value })}
          />
        </label>
        <label>
          Version
          <input
            type="text"
            value={identity.version}
            placeholder="e.g. 1.0.0"
            onChange={(e) => onChange({ version: e.target.value })}
          />
        </label>
        <label>
          Name
          <input
            type="text"
            value={identity.name}
            placeholder="Human-readable name"
            onChange={(e) => onChange({ name: e.target.value })}
          />
        </label>
      </div>
    </div>
  );
}

function ReviewTable({
  items,
  onAccept,
  onReset,
}: {
  items: ReviewItem[];
  onAccept: (reviewId: string, value: string) => void;
  onReset: (reviewId: string) => void;
}) {
  const groups = useMemo(() => {
    const m = new Map<string, ReviewItem[]>();
    for (const it of items) {
      const key = `${it.artifact_id}::${it.item_id}`;
      if (!m.has(key)) m.set(key, []);
      m.get(key)!.push(it);
    }
    return [...m.entries()];
  }, [items]);

  if (!items.length) return <p className="muted">No review items in this set.</p>;

  return (
    <table>
      <thead>
        <tr>
          <th style={{ width: "14%" }}>Field</th>
          <th style={{ width: "20%" }}>Current value</th>
          <th style={{ width: "34%" }}>Suggested value (editable)</th>
          <th style={{ width: "12%" }}>Status</th>
          <th style={{ width: "20%" }}>Action</th>
        </tr>
      </thead>
      <tbody>
        {groups.map(([key, rows]) => (
          <GroupRows key={key} rows={rows} onAccept={onAccept} onReset={onReset} />
        ))}
      </tbody>
    </table>
  );
}

function GroupRows({
  rows,
  onAccept,
  onReset,
}: {
  rows: ReviewItem[];
  onAccept: (reviewId: string, value: string) => void;
  onReset: (reviewId: string) => void;
}) {
  const head = rows[0];
  return (
    <>
      <tr className="group-head">
        <td colSpan={5}>
          {head.item_id} — {head.item_label}
          {head.parent_id && <span className="muted"> (parent: {head.parent_id})</span>}
          <span className="muted"> · {head.artifact_id}</span>
        </td>
      </tr>
      {rows.map((r) => (
        <FieldRow key={r.review_id} item={r} onAccept={onAccept} onReset={onReset} />
      ))}
    </>
  );
}

function FieldRow({
  item,
  onAccept,
  onReset,
}: {
  item: ReviewItem;
  onAccept: (reviewId: string, value: string) => void;
  onReset: (reviewId: string) => void;
}) {
  const stored = (item.status === "edited" ? item.edited_value : item.suggested_value) ?? "";
  const [draft, setDraft] = useState(stored);

  useEffect(() => setDraft(stored), [stored]);

  const locked = item.status !== "pending";

  return (
    <tr>
      <td>{item.field}</td>
      <td className="muted">{item.current_value === null ? "(new)" : item.current_value || "—"}</td>
      <td>
        <input
          type="text"
          value={draft}
          disabled={locked}
          onChange={(e) => setDraft(e.target.value)}
        />
      </td>
      <td>
        <span className={`badge ${item.status}`}>{item.status}</span>
      </td>
      <td>
        {locked ? (
          <button onClick={() => onReset(item.review_id)}>Undo</button>
        ) : (
          <button className="tick" onClick={() => onAccept(item.review_id, draft)}>
            ✓ Accept
          </button>
        )}
      </td>
    </tr>
  );
}
