"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

type SessionSummary = {
  id: string;
  created_at: string;
  filenames: string[];
  active: boolean;
};

export default function SetsPage() {
  const router = useRouter();
  const [sessions, setSessions] = useState<SessionSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);

  function load() {
    fetch("/api/sessions")
      .then((r) => r.json())
      .then((j) => setSessions(j.sessions ?? []))
      .finally(() => setLoading(false));
  }

  useEffect(load, []);

  async function reopen(id: string) {
    setBusyId(id);
    await fetch("/api/sessions/activate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ session_id: id }),
    });
    router.push("/review");
  }

  if (loading) return <p>Loading…</p>;

  return (
    <>
      <h1>Processed Files</h1>
      <p className="hint">
        Every file that has been uploaded and processed, as a retrievable set. Reopen one to
        review or edit it again &mdash; this becomes the active set in Metadata Review, Data
        Preview, and Export.
      </p>

      {sessions.length === 0 ? (
        <p className="muted">Nothing processed yet.</p>
      ) : (
        <table>
          <thead>
            <tr>
              <th style={{ width: "40%" }}>File</th>
              <th style={{ width: "25%" }}>Processed at</th>
              <th style={{ width: "15%" }}>Status</th>
              <th style={{ width: "20%" }}>Action</th>
            </tr>
          </thead>
          <tbody>
            {sessions.map((s) => (
              <tr key={s.id}>
                <td>{s.filenames.join(", ") || "(unknown file)"}</td>
                <td className="muted">{new Date(s.created_at).toLocaleString()}</td>
                <td>{s.active ? <span className="ok">active</span> : <span className="muted">—</span>}</td>
                <td>
                  <button disabled={busyId === s.id} onClick={() => reopen(s.id)}>
                    {busyId === s.id ? "Opening…" : s.active ? "Open" : "Reopen"}
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </>
  );
}
