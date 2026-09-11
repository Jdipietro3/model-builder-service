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
      <div className="rounded-xl border border-alarm/40 bg-alarm-wash px-4 py-3">
        <div className="mb-1 text-sm font-medium text-alarm">Training failed</div>
        {error && (
          <pre className="max-h-40 overflow-auto whitespace-pre-wrap font-mono text-xs text-alarm/80">
            {error}
          </pre>
        )}
      </div>
    );
  }

  // A run that has not started yet gets no meter. The bar below floors its width
  // at 2% and pairs it with a pulsing dot, which together read as "working, but
  // frozen at 0%" — exactly the wrong story for a tournament ensemble, which
  // legitimately cannot begin until its candidates finish. Say that instead.
  if (status === "waiting" || status === "claimed") {
    return (
      <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
        <div className="flex items-center gap-2 text-sm text-zinc-400">
          <span className="h-2 w-2 rounded-full bg-zinc-600" />
          {progress?.message ?? "Waiting for tournament candidates to finish"}
        </div>
      </div>
    );
  }

  const pct = progress?.pct ?? 0;
  return (
    <div className="rounded-xl border border-zinc-800 bg-zinc-900/60 px-4 py-3">
      <div className="mb-2 flex items-center justify-between text-sm">
        <span className="flex items-center gap-2 text-zinc-300">
          <span className="h-2 w-2 animate-pulse rounded-full bg-info" />
          {progress?.message ?? (status === "queued" ? "Waiting for a worker" : "Training")}
        </span>
        <span
          className="font-mono text-xs text-accent-bright"
          style={{ fontVariantNumeric: "tabular-nums" }}
        >
          {pct}%
        </span>
      </div>
      {/* Meter: accent-dim fill on the zinc-800 track */}
      <div className="h-2 overflow-hidden rounded-full bg-zinc-800">
        <div
          className="h-full rounded-full bg-accent-dim transition-all duration-700"
          style={{ width: `${Math.max(pct, 2)}%` }}
        />
      </div>
    </div>
  );
}
