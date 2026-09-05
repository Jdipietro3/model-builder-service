"use client";

import { api, Prediction } from "@/lib/api";

// Same sequential hue as ReportCard's magnitude encodings, sourced from the
// shared chart palette in globals.css.
const SEQ_HUE = "var(--chart-seq)";

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
          <span className="rounded bg-info-wash px-2 py-0.5 text-xs font-medium text-info">
            PREDICTIONS
          </span>
          <span className="font-mono text-sm text-zinc-300">{prediction.filename}</span>
          <span className="text-xs text-zinc-400">
            {prediction.n_rows.toLocaleString()} rows ·{" "}
            {new Date(prediction.created_at).toLocaleString()}
          </span>
        </div>
        <a
          href={api.predictionDownloadUrl(prediction.id)}
          className="focus-ring-panel rounded px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-accent"
        >
          ↓ Download scored CSV
        </a>
      </div>

      <div className="space-y-4 px-4 py-4">
        {counts && (
          <div>
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
              Predicted classes
            </h3>
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
                      className="text-xs text-zinc-400"
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
            <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
              Predicted values
            </h3>
            <div className="grid grid-cols-3 gap-2">
              {(["mean", "min", "max"] as const).map((k) => (
                <div key={k} className="rounded-lg bg-zinc-950/40 px-3 py-2.5">
                  <div className="text-xs text-zinc-400">{k}</div>
                  <div className="font-mono text-lg font-semibold text-accent-bright">
                    {fmt(summary.stats![k])}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        <div>
          <h3 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
            Preview (first {summary.preview.rows.length} rows)
          </h3>
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs" style={{ fontVariantNumeric: "tabular-nums" }}>
              <thead>
                <tr className="border-b border-zinc-800">
                  {summary.preview.columns.map((col) => (
                    <th
                      key={col}
                      className={`whitespace-nowrap px-3 py-2 font-mono font-medium ${
                        emphasized(col) ? "bg-info-wash text-info" : "text-zinc-400"
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
                            ? "bg-info-wash/60 text-info"
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
