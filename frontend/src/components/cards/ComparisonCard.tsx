"use client";

import { Results } from "@/lib/api";
import { LOWER_BETTER, METRIC_LABELS, fmt } from "./ReportCard";

const GOOD = "#0ca30c";
const BAD = "#e66767";

function ComparisonMetricTile({
  name,
  oldValue,
  newValue,
  primary,
}: {
  name: string;
  oldValue: number;
  newValue: number;
  primary: boolean;
}) {
  const lowerBetter = LOWER_BETTER.has(name);
  const delta = newValue - oldValue;
  const improved = lowerBetter ? delta < 0 : delta > 0;
  const deltaSign = delta > 0 ? "+" : "";
  return (
    <div
      className={`rounded-lg border px-3 py-2.5 ${
        primary ? "border-zinc-600 bg-zinc-800/60" : "border-zinc-800 bg-zinc-900/40"
      }`}
    >
      <div className="text-xs text-zinc-500">
        {METRIC_LABELS[name] ?? name}
        {primary && <span className="ml-1.5 text-[10px] text-emerald-500">optimized</span>}
      </div>
      <div
        className={`flex items-baseline gap-1.5 font-semibold text-zinc-100 ${
          primary ? "text-lg" : "text-sm"
        }`}
      >
        <span className="text-zinc-500 line-through decoration-zinc-600">{fmt(oldValue)}</span>
        <span className="text-zinc-600">→</span>
        <span>{fmt(newValue)}</span>
      </div>
      <div
        className="mt-1 text-xs"
        style={{ color: delta === 0 ? "#71717a" : improved ? GOOD : BAD }}
      >
        {delta === 0
          ? "no change"
          : `${deltaSign}${fmt(delta)} ${improved ? "▲ better" : "▼ worse"}`}
      </div>
    </div>
  );
}

export default function ComparisonCard({
  oldResults,
  newResults,
  oldDatasetVersion,
  newDatasetVersion,
}: {
  oldResults: Results;
  newResults: Results;
  oldDatasetVersion?: number;
  newDatasetVersion?: number;
}) {
  const primary = newResults.primary_metric;
  const newMetrics = newResults.holdout.metrics;
  const oldMetrics = oldResults.holdout.metrics;
  const sharedKeys = Object.keys(newMetrics).filter((k) => k in oldMetrics);
  if (sharedKeys.length === 0) return null;
  const secondary = sharedKeys.filter((k) => k !== primary);
  const orderedKeys = sharedKeys.includes(primary) ? [primary, ...secondary] : secondary;

  const isForecasting =
    newResults.task_family === "forecasting" || newResults.task_type === "forecasting";

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900/80">
      <div className="border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-sky-950 px-2 py-0.5 text-xs font-medium text-sky-300">
            COMPARISON
          </span>
          <span className="text-sm text-zinc-300">Retrained on updated data</span>
        </div>
        <div className="mt-0.5 text-xs text-zinc-500">
          vs previous run
          {oldDatasetVersion && newDatasetVersion
            ? ` (v${oldDatasetVersion} → v${newDatasetVersion})`
            : ""}
        </div>
      </div>

      <div className="space-y-4 px-4 py-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          {orderedKeys.map((k) => (
            <ComparisonMetricTile
              key={k}
              name={k}
              oldValue={oldMetrics[k]}
              newValue={newMetrics[k]}
              primary={k === primary}
            />
          ))}
        </div>
        <p className="text-xs text-zinc-500">
          n_train {oldResults.n_train.toLocaleString()} → {newResults.n_train.toLocaleString()}
          {isForecasting && newResults.freq ? ` · freq ${newResults.freq}` : ""}
          {isForecasting && newResults.horizon ? ` · horizon ${newResults.horizon}` : ""}
        </p>
      </div>
    </div>
  );
}
