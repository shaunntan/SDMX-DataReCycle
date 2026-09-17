"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

type Preview = { columns: string[]; rows: unknown[][]; row_count: number };
type ConversionData = { script: string | null; preview: Preview | null; has_parquet: boolean };
type DataConversionStatus = { status: string; error: string | null };

function stemFromFilename(filename: string): string {
  return filename.replace(/\.[^.]+$/, "");
}

export default function DataPreviewPage() {
  const [loading, setLoading] = useState(true);
  const [filenames, setFilenames] = useState<string[]>([]);
  const [dataConversion, setDataConversion] = useState<Record<string, DataConversionStatus>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [data, setData] = useState<Record<string, ConversionData>>({});
  const [showScript, setShowScript] = useState(false);

  useEffect(() => {
    fetch("/api/session")
      .then((r) => r.json())
      .then((j) => {
        if (j.session) {
          setFilenames(j.session.filenames ?? []);
          setDataConversion(j.session.dataConversion ?? {});
          const first = Object.keys(j.session.dataConversion ?? {})[0];
          if (first) setSelected(first);
        }
      })
      .finally(() => setLoading(false));
  }, []);

  const stem = useMemo(() => (filenames[0] ? stemFromFilename(filenames[0]) : null), [filenames]);
  const dsdIds = Object.keys(dataConversion);

  useEffect(() => {
    if (!selected || !stem || data[selected]) return;
    fetch(`/api/data-conversion?stem=${encodeURIComponent(stem)}&dsd_id=${encodeURIComponent(selected)}`)
      .then((r) => r.json())
      .then((j) => setData((d) => ({ ...d, [selected]: j })));
  }, [selected, stem, data]);

  if (loading) return <p>Loading…</p>;

  if (!stem || dsdIds.length === 0) {
    return (
      <>
        <h1>Data Preview</h1>
        <p>
          No processed dataset yet. <Link href="/upload">Upload a report</Link> first.
        </p>
      </>
    );
  }

  const current = selected ? dataConversion[selected] : null;
  const currentData = selected ? data[selected] : null;

  return (
    <>
      <h1>Data Preview</h1>
      <p className="hint">
        Codex-generated conversion of the report into Parquet, shaped by each DSD&apos;s
        dimensions/attributes/measure. Showing up to 30 rows per dataset.
      </p>

      <div className="row">
        {dsdIds.map((id) => (
          <button
            key={id}
            className={id === selected ? "on" : ""}
            onClick={() => {
              setSelected(id);
              setShowScript(false);
            }}
          >
            {id} <span className={dataConversion[id].status === "SUCCESS" ? "ok" : dataConversion[id].status === "FAILED" ? "bad" : "muted"}>
              {dataConversion[id].status}
            </span>
          </button>
        ))}
      </div>

      {current?.status === "RUNNING" && <p className="muted">Still converting…</p>}

      {current?.status === "FAILED" && (
        <div className="box">
          <p className="bad">Conversion failed: {current.error}</p>
          {currentData?.script && (
            <>
              <button onClick={() => setShowScript((s) => !s)}>
                {showScript ? "Hide" : "Show"} generated script
              </button>
              {showScript && <pre className="code-block">{currentData.script}</pre>}
            </>
          )}
        </div>
      )}

      {current?.status === "SUCCESS" && currentData?.preview && (
        <>
          <p className="muted">{currentData.preview.row_count} total rows.</p>
          <div style={{ overflowX: "auto" }}>
            <table>
              <thead>
                <tr>
                  {currentData.preview.columns.map((c) => (
                    <th key={c}>{c}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {currentData.preview.rows.map((row, i) => (
                  <tr key={i}>
                    {row.map((cell, j) => (
                      <td key={j}>{cell === null ? "—" : String(cell)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {currentData.script && (
            <div className="row">
              <button onClick={() => setShowScript((s) => !s)}>
                {showScript ? "Hide" : "Show"} generated script
              </button>
            </div>
          )}
          {showScript && <pre className="code-block">{currentData.script}</pre>}
        </>
      )}
    </>
  );
}
