"use client";

import { useEffect, useRef, useState } from "react";
import { Dataset, Methodology, Plan, Prediction, Run } from "@/lib/api";
import { RunState } from "@/app/projects/[id]/page";
import ProfileCard from "./cards/ProfileCard";
import PlanCard from "./cards/PlanCard";
import TrainingCard from "./cards/TrainingCard";
import ReportCard from "./cards/ReportCard";
import PredictionCard from "./cards/PredictionCard";

const STATUS_DOT: Record<string, string> = {
  pending_approval: "bg-amber-400",
  queued: "bg-sky-400",
  running: "bg-sky-400",
  completed: "bg-emerald-500",
  failed: "bg-red-500",
};

function extractErrorDetail(e: unknown): string {
  const msg = String(e instanceof Error ? e.message : e);
  const jsonStart = msg.indexOf("{");
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(msg.slice(jsonStart));
      if (parsed.detail) return String(parsed.detail);
    } catch {
      // fall through to raw message
    }
  }
  return msg;
}

function DatasetSection({
  datasets,
  onUploadDataset,
}: {
  datasets: Dataset[];
  onUploadDataset: (f: File) => void;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (datasets.length === 0) return null;
  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500">Data</h2>
        <label className="cursor-pointer text-xs text-zinc-500 transition-colors hover:text-emerald-400">
          <input
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUploadDataset(f);
              e.target.value = "";
            }}
          />
          + Add dataset
        </label>
      </div>
      <div className="space-y-2">
        {datasets.map((d) => (
          <div key={d.id}>
            <button
              onClick={() => setOpen((prev) => ({ ...prev, [d.id]: !prev[d.id] }))}
              className="flex w-full items-center justify-between rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2.5 text-left transition-colors hover:border-zinc-700"
            >
              <span className="font-mono text-sm text-zinc-300">{d.filename}</span>
              <span className="text-xs text-zinc-500">
                {d.profile
                  ? `${d.profile.n_rows.toLocaleString()} rows × ${d.profile.n_cols} cols`
                  : ""}{" "}
                {open[d.id] ? "▾" : "▸"}
              </span>
            </button>
            {open[d.id] && (
              <div className="mt-2">
                <ProfileCard filename={d.filename} profile={d.profile} />
              </div>
            )}
          </div>
        ))}
      </div>
    </section>
  );
}

function PredictSection({
  run,
  predictions,
  onPredict,
}: {
  run: Run;
  predictions: Prediction[];
  onPredict: (runId: string, file: File) => Promise<void>;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  async function handleFile(file: File) {
    setBusy(true);
    setError(null);
    try {
      await onPredict(run.id, file);
    } catch (e) {
      setError(extractErrorDetail(e));
    } finally {
      setBusy(false);
    }
  }

  const runPredictions = predictions
    .filter((p) => p.run_id === run.id)
    .slice()
    .reverse();

  return (
    <section>
      <div className="mb-2 flex items-center justify-between">
        <h2 className="text-xs font-medium uppercase tracking-wide text-zinc-500">
          Predict on new data
        </h2>
        <label
          className={`cursor-pointer rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 ${
            busy ? "pointer-events-none opacity-40" : ""
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) handleFile(f);
              e.target.value = "";
            }}
          />
          {busy ? "Scoring…" : "Upload CSV to score"}
        </label>
      </div>
      <p className="mb-3 text-xs text-zinc-500">
        Upload a CSV with the same feature columns (the target column isn&apos;t needed). The
        trained model appends a <span className="font-mono">prediction</span> column
        {run.plan.task_type !== "regression" && " and per-class probabilities"}.
      </p>
      {error && (
        <div className="mb-3 rounded-lg border border-red-900 bg-red-950/40 px-4 py-2.5 text-sm text-red-300">
          {error}
        </div>
      )}
      <div className="space-y-3">
        {runPredictions.map((p) => (
          <PredictionCard key={p.id} prediction={p} />
        ))}
      </div>
    </section>
  );
}

export default function Workspace({
  datasets,
  runs,
  runStates,
  predictions,
  methodologies,
  onApprove,
  onPredict,
  onUploadDataset,
}: {
  datasets: Dataset[];
  runs: Run[];
  runStates: Record<string, RunState>;
  predictions: Prediction[];
  methodologies: Methodology[];
  onApprove: (runId: string, overrides: Partial<Plan>) => void;
  onPredict: (runId: string, file: File) => Promise<void>;
  onUploadDataset: (file: File) => void;
}) {
  const ordered = runs.slice().reverse(); // newest first
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // Select the newest run whenever one appears (incl. a freshly proposed plan).
  useEffect(() => {
    if (ordered.length > 0) setSelectedId(ordered[0].id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [runs.length]);

  const selected = ordered.find((r) => r.id === selectedId) ?? ordered[0];
  if (!selected) return null;

  const state = runStates[selected.id];
  const status = state?.status ?? selected.status;
  const results = state?.results ?? selected.results;
  const dataset = datasets.find((d) => d.id === selected.dataset_id);
  const methodology = methodologies.find((m) => m.id === selected.plan.methodology_id);

  return (
    <div className="space-y-8">
      <DatasetSection datasets={datasets} onUploadDataset={onUploadDataset} />

      <section>
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">Model</h2>
        {ordered.length > 1 && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {ordered.map((r) => {
              const s = runStates[r.id]?.status ?? r.status;
              const m = methodologies.find((x) => x.id === r.plan.methodology_id);
              return (
                <button
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors ${
                    r.id === selected.id
                      ? "border-zinc-500 bg-zinc-800 text-zinc-100"
                      : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
                  }`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[s] ?? "bg-zinc-500"}`} />
                  {m?.display_name ?? r.plan.methodology_id} → {r.plan.target_column}
                </button>
              );
            })}
          </div>
        )}
        <div className="space-y-3">
          <PlanCard
            runId={selected.id}
            datasetFilename={dataset?.filename ?? ""}
            plan={selected.plan}
            profile={dataset?.profile ?? null}
            methodologies={methodologies}
            status={status}
            onApprove={onApprove}
          />
          {["queued", "running", "failed"].includes(status) && (
            <TrainingCard
              status={status}
              progress={state?.progress ?? null}
              error={state?.error ?? null}
            />
          )}
          {status === "completed" && results && (
            <ReportCard runId={selected.id} results={results} />
          )}
        </div>
      </section>

      {/* Batch scoring doesn't apply to forecasting runs (the backend rejects it). */}
      {status === "completed" && selected.plan.task_type !== "forecasting" && (
        <PredictSection run={selected} predictions={predictions} onPredict={onPredict} />
      )}

      {methodology && (
        <p className="pb-6 text-xs leading-relaxed text-zinc-600">
          {methodology.display_name}: {methodology.when_to_use}
        </p>
      )}
    </div>
  );
}
