"use client";

/**
 * Score tab: run the selected model over new rows and get a CSV back.
 *
 * This is data you predict ON, as distinct from the training data in the Data
 * tab. It works as its own tab because the run it scores with comes from the
 * rail's model dropdown — without that ambient selection it would need a second
 * picker, and a user could score with a model other than the one they were
 * looking at.
 *
 * Batch scoring doesn't apply to forecasting runs (the backend rejects it).
 */

import { useRef, useState } from "react";
import { useProject } from "@/lib/project-context";
import { extractErrorDetail } from "@/lib/errors";
import PredictionCard from "@/components/cards/PredictionCard";
import EmptyTab from "@/components/tabs/EmptyTab";

export default function ScoreTab() {
  const { predictions, runStates, selectedRun: run, handlePredict } = useProject();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    if (!run) return;
    setBusy(true);
    setError(null);
    try {
      await handlePredict(run.id, file);
    } catch (e) {
      setError(extractErrorDetail(e));
    } finally {
      setBusy(false);
    }
  }

  const heading = <h2 className="text-headline font-semibold text-zinc-100">Score new data</h2>;

  if (!run) {
    return (
      <section className="space-y-3">
        {heading}
        <EmptyTab
          title="No model to score with"
          body="Train a model first — the Model tab will walk you through it."
        />
      </section>
    );
  }

  const status = runStates[run.id]?.status ?? run.status;

  if (status !== "completed") {
    return (
      <section className="space-y-3">
        {heading}
        <EmptyTab
          title="This model isn't ready"
          body="Only a completed run can score new rows. Pick a finished model in the sidebar, or wait for this one to train."
        />
      </section>
    );
  }

  if (run.plan.task_type === "forecasting") {
    return (
      <section className="space-y-3">
        {heading}
        <EmptyTab
          title="Not available for forecasting"
          body="Forecasting runs project forward from their own history rather than scoring supplied rows. The forecast is on the Metrics tab."
        />
      </section>
    );
  }

  const runPredictions = predictions
    .filter((p) => p.run_id === run.id)
    .slice()
    .reverse();

  return (
    <section>
      <div className="mb-3 flex items-center justify-between">
        {heading}
        <button
          type="button"
          disabled={busy}
          onClick={() => inputRef.current?.click()}
          className="focus-ring cursor-pointer rounded-lg border border-zinc-700 bg-zinc-900 px-4 py-2 text-body font-medium text-zinc-200 transition-colors hover:bg-zinc-800 hover:text-emerald-300 disabled:pointer-events-none disabled:opacity-40"
        >
          {busy ? "Scoring…" : "Upload CSV to score"}
        </button>
        <input
          ref={inputRef}
          type="file"
          accept=".csv"
          className="sr-only"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
            e.target.value = "";
          }}
        />
      </div>
      <p className="measure mb-3 text-label text-zinc-400">
        Upload a CSV with the same feature columns (the target column isn&apos;t needed). The
        trained model appends a <span className="font-mono">prediction</span> column
        {run.plan.task_type !== "regression" && " and per-class probabilities"}.
      </p>
      {error && (
        <div className="mb-3 rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-body text-red-300">
          {error}
        </div>
      )}
      {runPredictions.length === 0 && !error ? (
        <EmptyTab
          title="Nothing scored yet"
          body="Upload a CSV above and the scored file will appear here to download."
        />
      ) : (
        <div className="space-y-3">
          {runPredictions.map((p) => (
            <PredictionCard key={p.id} prediction={p} />
          ))}
        </div>
      )}
    </section>
  );
}
