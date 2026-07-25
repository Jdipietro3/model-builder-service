"use client";

import { RunProgress } from "@/lib/api";

export default function TrainingCard({
  status,
  progress,
  error,
}: {
  status: string;
  progress: RunProgress | null;
  error: string | null;
}) {
  if (status === "failed") {
    return (
      <div className="rounded-xl border border-red-900 bg-red-950/40 px-4 py-3">
        <div className="mb-1 text-sm font-medium text-red-300">Training failed</div>
        {error && (
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-xs text-red-400/80">
            {error}
          </pre>
        )}
      </div>
    );
  }

  const pct = progress?.pct ?? 0;
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="flex items-center gap-2 text-zinc-300">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
          {progress?.message ?? (status === "queued" ? "Waiting for a worker" : "Training")}
        </span>
        <span className="text-xs text-zinc-400" style={{ fontVariantNumeric: "tabular-nums" }}>
          {pct}%
        </span>
      </div>
      {/* Meter: emerald fill on a darker step of the same ramp */}
      <div className="h-2 overflow-hidden rounded-full bg-emerald-950">
        <div
          className="h-full rounded-full bg-emerald-500 transition-all duration-700"
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
    </div>
  );
}
