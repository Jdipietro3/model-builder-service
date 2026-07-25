"use client";

import { Results, Run } from "@/lib/api";
import { LOWER_BETTER, METRIC_LABELS, fmt } from "./ReportCard";

export interface Contender {
  run: Run;
  results: Results;
}

function columnLabel(c: Contender): string {
  return (
    c.results.methodology?.display_name ||
    (c.run.tournament_role === "ensemble" ? "Ensemble" : c.run.plan.methodology_id)
  );
}

export default function TournamentComparisonCard({
  contenders,
}: {
  contenders: Contender[];
}) {
  if (contenders.length < 2) return null;

  const primary = contenders[0]?.results.primary_metric;

  // Union of every contender's holdout metric keys, primary metric first.
  const allKeys = new Set<string>();
  contenders.forEach((c) => Object.keys(c.results.holdout.metrics).forEach((k) => allKeys.add(k)));
  const rest = [...allKeys].filter((k) => k !== primary).sort();
  const rows = primary && allKeys.has(primary) ? [primary, ...rest] : rest;

  // Best column per primary-metric row, used for the "best on primary metric" badge.
  let bestRunId: string | null = null;
  if (primary) {
    const lowerBetter = LOWER_BETTER.has(primary);
    let bestValue: number | null = null;
    for (const c of contenders) {
      const v = c.results.holdout.metrics[primary];
      if (v === undefined || !Number.isFinite(v)) continue;
      if (
        bestValue === null ||
        (lowerBetter ? v < bestValue : v > bestValue)
      ) {
        bestValue = v;
        bestRunId = c.run.id;
      }
    }
  }

  function bestRunIdForRow(key: string): string | null {
    const lowerBetter = LOWER_BETTER.has(key);
    let best: number | null = null;
    let bestId: string | null = null;
    for (const c of contenders) {
      const v = c.results.holdout.metrics[key];
      if (v === undefined || !Number.isFinite(v)) continue;
      if (best === null || (lowerBetter ? v < best : v > best)) {
        best = v;
        bestId = c.run.id;
      }
    }
    return bestId;
  }

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900/80">
      <div className="border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-violet-950 px-2 py-0.5 text-xs font-medium text-violet-300">
            TOURNAMENT COMPARISON
          </span>
          <span className="text-sm text-zinc-300">{contenders.length}-way</span>
        </div>
        <p className="measure mt-1 text-xs text-zinc-400">
          Metrics on the shared holdout split. No hard winner is claimed here — check the chat
          for the assistant&apos;s read.
        </p>
      </div>

      <div className="overflow-x-auto px-4 py-4">
        <table className="w-full min-w-max text-sm" style={{ fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr>
              <th className="px-2 pb-2 text-left text-xs font-medium uppercase tracking-wide text-zinc-400">
                Metric
              </th>
              {contenders.map((c) => (
                <th key={c.run.id} className="px-3 pb-2 text-left">
                  <div className="flex items-center gap-1.5">
                    <span className="text-xs font-medium text-zinc-200">{columnLabel(c)}</span>
                    {c.run.id === bestRunId && (
                      <span className="rounded bg-emerald-950 px-1.5 py-0.5 text-xs font-medium text-emerald-300">
                        best on primary metric
                      </span>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((key) => {
              const isPrimary = key === primary;
              const bestId = bestRunIdForRow(key);
              return (
                <tr
                  key={key}
                  className={isPrimary ? "bg-zinc-800/40" : ""}
                >
                  <td className="whitespace-nowrap px-2 py-1.5 text-xs text-zinc-400">
                    {METRIC_LABELS[key] ?? key}
                    {isPrimary && (
                      <span className="ml-1.5 text-xs text-emerald-500">optimized</span>
                    )}
                  </td>
                  {contenders.map((c) => {
                    const v = c.results.holdout.metrics[key];
                    const isBest = c.run.id === bestId && v !== undefined;
                    return (
                      <td
                        key={c.run.id}
                        className={`whitespace-nowrap px-3 py-1.5 ${
                          isBest ? "font-semibold text-emerald-300" : "text-zinc-200"
                        }`}
                      >
                        {v === undefined ? "—" : fmt(v)}
                      </td>
                    );
                  })}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
