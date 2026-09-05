"use client";

import { Results } from "@/lib/api";
import { LOWER_BETTER, METRIC_LABELS, fmt } from "./ReportCard";

// Sourced from the shared chart palette in globals.css so there is one
// vocabulary for "improved / regressed / unchanged" across every chart.
const GOOD = "var(--chart-good)";
const BAD = "var(--chart-bad)";
// --chart-neutral (Ink Inert) is non-text only per DESIGN.md; the zero-delta
// case below renders text, so it uses the readable axis/muted tone instead.
const NEUTRAL_TEXT = "var(--chart-axis)";

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
      // Background shift, not a nested border: these tiles sit inside an
      // already-bordered card, and a box inside a box is a nested card.
      className={`rounded-lg px-3 py-2.5 ${primary ? "bg-zinc-800/80" : "bg-zinc-950/40"}`}
    >
      <div className="text-xs text-zinc-400">
        {METRIC_LABELS[name] ?? name}
        {primary && <span className="ml-1.5 text-xs text-accent">optimized</span>}
      </div>
      <div
        className={`flex items-baseline gap-1.5 font-mono font-semibold ${
          primary ? "text-lg" : "text-sm"
        }`}
      >
        <span className="text-zinc-400 line-through decoration-zinc-600">{fmt(oldValue)}</span>
        <span className="text-zinc-400">→</span>
        <span className="text-accent-bright">{fmt(newValue)}</span>
      </div>
      <div
        className="mt-1 text-xs"
        style={{ color: delta === 0 ? NEUTRAL_TEXT : improved ? GOOD : BAD }}
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
          <span className="rounded bg-info-wash px-2 py-0.5 text-xs font-medium text-info">
            COMPARISON
          </span>
          <span className="text-sm text-zinc-300">Retrained on updated data</span>
        </div>
        <div className="mt-0.5 text-xs text-zinc-400">
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
        <p className="text-xs text-zinc-400">
          n_train {oldResults.n_train.toLocaleString()} → {newResults.n_train.toLocaleString()}
          {isForecasting && newResults.freq ? ` · freq ${newResults.freq}` : ""}
          {isForecasting && newResults.horizon ? ` · horizon ${newResults.horizon}` : ""}
        </p>
      </div>
    </div>
  );
}
