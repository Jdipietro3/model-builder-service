"use client";

import { api, Prediction } from "@/lib/api";

// Same sequential hue as ReportCard's magnitude encodings.
const SEQ_HUE = "#3987e5";

function fmt(v: number): string {
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return v.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

export default function PredictionCard({ prediction }: { prediction: Prediction }) {
  const { summary } = prediction;
  const counts = summary.class_counts;
  const maxCount = counts ? Math.max(...Object.values(counts)) : 0;
  const emphasized = (col: string) => col === "prediction" || col.startsWith("prob_");

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/60">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-sky-950 px-2 py-0.5 text-xs font-medium text-sky-300">
            PREDICTIONS
          </span>
          <span className="font-mono text-sm text-zinc-300">{prediction.filename}</span>
          <span className="text-xs text-zinc-500">
            {prediction.n_rows.toLocaleString()} rows ·{" "}
            {new Date(prediction.created_at).toLocaleString()}
          </span>
        </div>
        <a
          href={api.predictionDownloadUrl(prediction.id)}
          className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-emerald-600 hover:text-emerald-400"
        >
          ↓ Download scored CSV
        </a>
      </div>

      <div className="space-y-4 px-4 py-4">
        {counts && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
              Predicted classes
            </h4>
            <div className="space-y-1.5">
              {Object.entries(counts).map(([cls, n]) => (
                <div key={cls} className="flex items-center gap-2" title={`${cls}: ${n} rows`}>
                  <span className="w-24 shrink-0 truncate text-right font-mono text-xs text-zinc-300">
                    {cls}
                  </span>
                  <div className="flex flex-1 items-center gap-2">
                    <div
                      className="h-3.5 rounded-r"
                      style={{
                        width: `${(n / maxCount) * 100}%`,
                        minWidth: 2,
                        background: SEQ_HUE,
                      }}
                    />
                    <span
                      className="text-xs text-zinc-500"
                      style={{ fontVariantNumeric: "tabular-nums" }}
                    >
                      {n.toLocaleString()} ({((n / summary.n_rows) * 100).toFixed(1)}%)
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {summary.stats && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
              Predicted values
            </h4>
            <div className="grid grid-cols-3 gap-2">
              {(["mean", "min", "max"] as const).map((k) => (
                <div key={k} className="rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-2.5">
                  <div className="text-xs text-zinc-500">{k}</div>
                  <div className="text-lg font-semibold text-zinc-100">
                    {fmt(summary.stats![k])}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
            Preview (first {summary.preview.rows.length} rows)
          </h4>
          <div className="overflow-x-auto rounded-lg border border-zinc-800">
            <table className="w-full text-left text-xs" style={{ fontVariantNumeric: "tabular-nums" }}>
              <thead>
                <tr className="border-b border-zinc-800">
                  {summary.preview.columns.map((col) => (
                    <th
                      key={col}
                      className={`whitespace-nowrap px-3 py-2 font-mono font-medium ${
                        emphasized(col) ? "bg-sky-950/40 text-sky-300" : "text-zinc-500"
                      }`}
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {summary.preview.rows.map((row, i) => (
                  <tr key={i} className="border-b border-zinc-800/50 last:border-0">
                    {row.map((cell, j) => (
                      <td
                        key={j}
                        className={`whitespace-nowrap px-3 py-1.5 font-mono ${
                          emphasized(summary.preview.columns[j])
                            ? "bg-sky-950/20 text-zinc-100"
                            : "text-zinc-400"
                        }`}
                      >
                        {cell}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
