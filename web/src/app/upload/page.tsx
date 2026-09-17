"use client";

import { useRouter } from "next/navigation";
import { useRef, useState } from "react";

export default function UploadPage() {
  const router = useRouter();
  const inputRef = useRef<HTMLInputElement>(null);
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit() {
    setError(null);
    if (!files.length) {
      setError("Select at least one file.");
      return;
    }
    setBusy(true);
    try {
      const fd = new FormData();
      files.forEach((f) => fd.append("files", f));
      const res = await fetch("/api/upload", { method: "POST", body: fd });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error ?? "Upload failed");
      router.push(`/processing?job=${json.job_id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Upload reports</h1>
      <p className="hint">
        Select one or more aggregate statistical report files (e.g. Excel) to process into SDMX
        metadata.
      </p>
      <div className="stubnote">
        Submitting runs the real report-to-SDMX pipeline (PrototypeCodes/) in the background for
        Concept Scheme, Codelists, and DSD/Key Family only — this can take several minutes. Only
        the first selected file is processed. Dataflow, MSD, Metadata Set, AI Fillable Data
        Template, and Codebook/Source Mapping are generated on disk by the same pipeline but not
        yet shown in Metadata Review.
      </div>

      <input
        ref={inputRef}
        type="file"
        multiple
        accept=".xlsx,.xls,.csv"
        onChange={(e) => setFiles(Array.from(e.target.files ?? []))}
        disabled={busy}
      />

      {files.length > 0 && (
        <ul>
          {files.map((f) => (
            <li key={f.name}>
              {f.name} <span className="muted">({Math.max(1, Math.round(f.size / 1024))} KB)</span>
            </li>
          ))}
        </ul>
      )}

      <div className="row">
        <button className="primary" onClick={submit} disabled={busy || files.length === 0}>
          {busy ? "Processing…" : "Submit"}
        </button>
        <button
          onClick={() => {
            setFiles([]);
            if (inputRef.current) inputRef.current.value = "";
          }}
          disabled={busy}
        >
          Clear
        </button>
      </div>

      {error && <p className="bad">{error}</p>}
    </>
  );
}
