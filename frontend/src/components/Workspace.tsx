"use client";

import { useEffect, useRef, useState } from "react";
import { Dataset, Deployment, Methodology, Plan, Prediction, Run } from "@/lib/api";
import { RunState } from "@/app/projects/[id]/page";
import ProfileCard from "./cards/ProfileCard";
import PlanCard from "./cards/PlanCard";
import TrainingCard from "./cards/TrainingCard";
import ReportCard from "./cards/ReportCard";
import ComparisonCard from "./cards/ComparisonCard";
import TournamentCard from "./cards/TournamentCard";
import TournamentComparisonCard, { Contender } from "./cards/TournamentComparisonCard";
import PredictionCard from "./cards/PredictionCard";
import DeploymentCard from "./cards/DeploymentCard";

/** A dataset is a chain tip if no other dataset's parent_dataset_id points at it. */
function isChainTip(d: Dataset, all: Dataset[]): boolean {
  return !all.some((x) => x.parent_dataset_id === d.id);
}

/** Walk parent_dataset_id links forward from `datasetId` to the newest version
 * in its chain (used to detect "a newer version exists" for the retrain CTA). */
function findChainTip(datasetId: string, all: Dataset[]): Dataset | undefined {
  let current = all.find((d) => d.id === datasetId);
  if (!current) return undefined;
  for (;;) {
    const next = all.find((d) => d.parent_dataset_id === current!.id);
    if (!next) return current;
    current = next;
  }
}

const STATUS_DOT: Record<string, string> = {
  pending_approval: "bg-amber-400",
  queued: "bg-sky-400",
  running: "bg-sky-400",
  waiting: "bg-zinc-500",
  claimed: "bg-zinc-500", // transient promotion-mutex state; treated like waiting
  completed: "bg-emerald-500",
  failed: "bg-red-500",
};

/** Statuses that mean "still working toward a result" for TrainingCard purposes,
 * including the ensemble's pre-promotion "waiting" state (and the brief
 * "claimed" state seen during promotion). */
function isTrainingLikeStatus(status: string): boolean {
  return ["queued", "running", "failed", "waiting", "claimed"].includes(status);
}

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

/** Inline "Update" control for a dataset chain tip: file picker, then a
 * Replace/Append/Cancel choice once a file is staged. */
function DatasetUpdateControl({
  dataset,
  onUploadDatasetUpdate,
}: {
  dataset: Dataset;
  onUploadDatasetUpdate: (datasetId: string, file: File, mode: "replace" | "append") => Promise<void>;
}) {
  const [pending, setPending] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit(mode: "replace" | "append") {
    if (!pending) return;
    setBusy(true);
    try {
      await onUploadDatasetUpdate(dataset.id, pending, mode);
    } catch {
      // Errors are surfaced by the caller (chat message); just reset locally.
    } finally {
      setBusy(false);
      setPending(null);
    }
  }

  if (pending) {
    return (
      <div className="flex shrink-0 items-center gap-1.5 text-xs" onClick={(e) => e.stopPropagation()}>
        <span className="max-w-28 truncate font-mono text-zinc-500" title={pending.name}>
          {pending.name}
        </span>
        <button
          onClick={() => submit("replace")}
          disabled={busy}
          className="rounded border border-zinc-700 px-2 py-0.5 text-zinc-300 transition-colors hover:border-emerald-600 hover:text-emerald-400 disabled:opacity-40"
        >
          Replace
        </button>
        <button
          onClick={() => submit("append")}
          disabled={busy}
          className="rounded border border-zinc-700 px-2 py-0.5 text-zinc-300 transition-colors hover:border-emerald-600 hover:text-emerald-400 disabled:opacity-40"
        >
          Append
        </button>
        <button
          onClick={() => setPending(null)}
          disabled={busy}
          title="Cancel"
          className="px-1 text-zinc-500 transition-colors hover:text-zinc-300 disabled:opacity-40"
        >
          ×
        </button>
      </div>
    );
  }

  return (
    <label
      className="shrink-0 cursor-pointer text-xs text-zinc-500 transition-colors hover:text-emerald-400"
      onClick={(e) => e.stopPropagation()}
    >
      <input
        type="file"
        accept=".csv"
        className="hidden"
        onChange={(e) => {
          const f = e.target.files?.[0];
          if (f) setPending(f);
          e.target.value = "";
        }}
      />
      Update
    </label>
  );
}

function DatasetSection({
  datasets,
  onUploadDataset,
  onUploadDatasetUpdate,
}: {
  datasets: Dataset[];
  onUploadDataset: (f: File) => void;
  onUploadDatasetUpdate: (datasetId: string, file: File, mode: "replace" | "append") => Promise<void>;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (datasets.length === 0) return null;
  // Only chain tips are shown — an updated dataset supersedes its parent in the list.
  const tips = datasets.filter((d) => isChainTip(d, datasets));
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
        {tips.map((d) => (
          <div key={d.id}>
            <div className="flex items-center gap-2 rounded-lg border border-zinc-800 bg-zinc-900/60 px-4 py-2.5 transition-colors hover:border-zinc-700">
              <button
                onClick={() => setOpen((prev) => ({ ...prev, [d.id]: !prev[d.id] }))}
                className="flex min-w-0 flex-1 items-center justify-between text-left"
              >
                <span className="flex items-center gap-1.5 truncate font-mono text-sm text-zinc-300">
                  {d.filename}
                  {(d.version ?? 1) > 1 && (
                    <span className="rounded bg-zinc-800 px-1.5 py-0.5 font-sans text-[10px] font-medium text-zinc-400">
                      v{d.version}
                    </span>
                  )}
                </span>
                <span className="shrink-0 pl-2 text-xs text-zinc-500">
                  {d.profile
                    ? `${d.profile.n_rows.toLocaleString()} rows × ${d.profile.n_cols} cols`
                    : ""}{" "}
                  {open[d.id] ? "▾" : "▸"}
                </span>
              </button>
              <DatasetUpdateControl dataset={d} onUploadDatasetUpdate={onUploadDatasetUpdate} />
            </div>
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
  deployments,
  methodologies,
  onApprove,
  onApproveTournament,
  onPredict,
  onUploadDataset,
  onRetrain,
  onUpdateDataset,
  onDeploy,
  onPromote,
  onSetStatus,
  recommendedRunId,
  recommendationReason,
}: {
  datasets: Dataset[];
  runs: Run[];
  runStates: Record<string, RunState>;
  predictions: Prediction[];
  deployments: Deployment[];
  methodologies: Methodology[];
  onApprove: (runId: string, overrides: Partial<Plan>) => void;
  onApproveTournament: (tournamentId: string) => void;
  onPredict: (runId: string, file: File) => Promise<void>;
  onUploadDataset: (file: File) => void;
  onRetrain: (runId: string) => Promise<void>;
  onUpdateDataset: (datasetId: string, file: File, mode: "replace" | "append") => Promise<void>;
  onDeploy: (runId: string, name?: string) => Promise<void>;
  onPromote: (deploymentId: string, runId: string) => Promise<void>;
  onSetStatus: (deploymentId: string, status: "active" | "disabled") => Promise<void>;
  recommendedRunId: string | null;
  recommendationReason: string | null;
}) {
  const ordered = runs.slice().reverse(); // newest first
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [retrainingIds, setRetrainingIds] = useState<Set<string>>(new Set());
  const [deployingIds, setDeployingIds] = useState<Set<string>>(new Set());

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

  // Newer data available for the selected run's dataset chain, if any.
  const datasetTip = findChainTip(selected.dataset_id, datasets);
  const hasNewerData = !!datasetTip && datasetTip.id !== selected.dataset_id;
  const retraining = retrainingIds.has(selected.id);

  async function handleRetrainClick() {
    setRetrainingIds((prev) => new Set(prev).add(selected.id));
    try {
      await onRetrain(selected.id);
    } finally {
      setRetrainingIds((prev) => {
        const next = new Set(prev);
        next.delete(selected.id);
        return next;
      });
    }
  }

  const deploying = deployingIds.has(selected.id);

  async function handleDeployClick() {
    setDeployingIds((prev) => new Set(prev).add(selected.id));
    try {
      await onDeploy(selected.id);
    } finally {
      setDeployingIds((prev) => {
        const next = new Set(prev);
        next.delete(selected.id);
        return next;
      });
    }
  }

  // Comparison vs. the run this one was retrained from (both need results).
  const parentRun = selected.parent_run_id
    ? runs.find((r) => r.id === selected.parent_run_id)
    : undefined;
  const parentResults = parentRun ? (runStates[parentRun.id]?.results ?? parentRun.results) : null;
  const parentDataset = parentRun ? datasets.find((d) => d.id === parentRun.dataset_id) : undefined;

  // Tournament siblings (candidates + ensemble) that share the selected run's
  // tournament_id and have results in — feeds the N-way comparison table below.
  const tournamentContenders: Contender[] = selected.tournament_id
    ? runs
        .filter((r) => r.tournament_id === selected.tournament_id)
        .map((r) => ({ run: r, results: runStates[r.id]?.results ?? r.results }))
        .filter((c): c is Contender => !!c.results)
    : [];

  // Pre-approval tournament grouping: while every candidate is still awaiting
  // approval, the whole tournament is approved once via TournamentCard (rendered
  // in place of the per-run PlanCard). Once training starts we fall through to the
  // normal per-run PlanCard / TrainingCard / ReportCard flow selected via the pills.
  const tournamentRuns = selected.tournament_id
    ? runs.filter((r) => r.tournament_id === selected.tournament_id)
    : [];
  const tCandidates = tournamentRuns.filter((r) => r.tournament_role === "candidate");
  const tEnsemble = tournamentRuns.find((r) => r.tournament_role === "ensemble") ?? null;
  const tournamentPending =
    tCandidates.length > 0 &&
    tCandidates.every((r) => (runStates[r.id]?.status ?? r.status) === "pending_approval");
  const ensembleKind: "blend" | "stacking" | "none" = tEnsemble
    ? tEnsemble.plan.methodology_id === "ensemble.stacking"
      ? "stacking"
      : "blend"
    : "none";

  // Live deployment is only offered for completed supervised/ensemble runs —
  // forecasting runs don't fit the single-record predict contract (mirrors the
  // same task_type check used below for the batch PredictSection).
  const canDeploy = status === "completed" && selected.plan.task_type !== "forecasting";
  const selectedDeployments = deployments.filter((d) => d.run_id === selected.id);

  // One deployment per project — if it exists but isn't serving the selected run,
  // offer to promote the selected run onto it instead of creating a new deployment.
  const projectDeployment = deployments[0] ?? null;
  const canPromoteToLive =
    !!projectDeployment &&
    projectDeployment.run_id !== selected.id &&
    status === "completed" &&
    selected.plan.task_type !== "forecasting" &&
    selected.plan.target_column === projectDeployment.contract.target_column &&
    selected.plan.task_type === projectDeployment.contract.task_type;

  // Synthesized progress for the ensemble's pre-promotion "waiting" state (and the
  // brief "claimed" state during promotion) when no live SSE progress has arrived yet.
  const trainingProgress =
    (status === "waiting" || status === "claimed") && !state?.progress
      ? { stage: "waiting", pct: 0, message: "Waiting for tournament candidates to finish" }
      : (state?.progress ?? null);

  return (
    <div className="space-y-8">
      <DatasetSection
        datasets={datasets}
        onUploadDataset={onUploadDataset}
        onUploadDatasetUpdate={onUpdateDataset}
      />

      <section>
        <h2 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">Model</h2>
        {ordered.length > 1 && (
          <div className="mb-3 flex flex-wrap gap-1.5">
            {ordered.map((r) => {
              const s = runStates[r.id]?.status ?? r.status;
              const m = methodologies.find((x) => x.id === r.plan.methodology_id);
              const v = datasets.find((d) => d.id === r.dataset_id)?.version ?? 1;
              const label = m?.display_name ?? (r.tournament_role === "ensemble" ? "Ensemble" : r.plan.methodology_id);
              const isRecommended = r.id === recommendedRunId;
              return (
                <button
                  key={r.id}
                  onClick={() => setSelectedId(r.id)}
                  className={`flex items-center gap-1.5 rounded-full border px-3 py-1 text-xs transition-colors ${
                    r.id === selected.id
                      ? "border-zinc-500 bg-zinc-800 text-zinc-100"
                      : "border-zinc-800 text-zinc-400 hover:border-zinc-600"
                  } ${r.tournament_id ? "border-l-2 border-l-violet-500" : ""} ${
                    isRecommended ? "ring-1 ring-emerald-500/70" : ""
                  }`}
                >
                  <span className={`h-1.5 w-1.5 rounded-full ${STATUS_DOT[s] ?? "bg-zinc-500"}`} />
                  {label} → {r.plan.target_column}
                  <span className="text-zinc-500">v{v}</span>
                  {isRecommended && (
                    <span className="flex items-center gap-0.5 rounded-full bg-emerald-500/15 px-1.5 py-0.5 text-[10px] font-medium text-emerald-400">
                      ★ Recommended
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        )}
        <div className="space-y-3">
          {selected.id === recommendedRunId && recommendationReason && (
            <div className="rounded-lg border border-emerald-900/60 bg-emerald-950/30 px-3 py-2.5">
              <div className="mb-1 text-xs font-medium text-emerald-300">
                ★ Recommended by the assistant
              </div>
              <p className="text-xs leading-relaxed text-emerald-200/80">{recommendationReason}</p>
            </div>
          )}
          {tournamentPending ? (
            <TournamentCard
              tournamentId={selected.tournament_id!}
              datasetFilename={dataset?.filename ?? ""}
              ensemble={ensembleKind}
              candidates={tCandidates.map((r) => ({ run_id: r.id, plan: r.plan }))}
              ensembleRun={tEnsemble ? { run_id: tEnsemble.id, plan: tEnsemble.plan } : null}
              reasoning={tCandidates[0]?.plan.reasoning ?? ""}
              methodologies={methodologies}
              runStates={runStates}
              onApproveTournament={onApproveTournament}
            />
          ) : (
            <PlanCard
              runId={selected.id}
              datasetFilename={dataset?.filename ?? ""}
              plan={selected.plan}
              profile={dataset?.profile ?? null}
              methodologies={methodologies}
              status={status}
              onApprove={onApprove}
            />
          )}
          {!tournamentPending && isTrainingLikeStatus(status) && (
            <TrainingCard status={status} progress={trainingProgress} error={state?.error ?? null} />
          )}
          {status === "completed" && results && (
            <ReportCard runId={selected.id} results={results} />
          )}
          {status === "completed" && results && parentRun && parentResults && (
            <ComparisonCard
              oldResults={parentResults}
              newResults={results}
              oldDatasetVersion={parentDataset?.version}
              newDatasetVersion={dataset?.version}
            />
          )}
          {selected.tournament_id && tournamentContenders.length >= 2 && (
            <TournamentComparisonCard contenders={tournamentContenders} />
          )}
          {status === "completed" && hasNewerData && (
            <button
              onClick={handleRetrainClick}
              disabled={retraining}
              className="rounded-lg border border-zinc-700 px-4 py-2 text-sm font-medium text-zinc-200 transition-colors hover:border-emerald-600 hover:text-emerald-400 disabled:opacity-40"
            >
              {retraining ? "Retraining…" : `Retrain on updated data (v${datasetTip?.version ?? 1})`}
            </button>
          )}
          {canDeploy && deployments.length === 0 && (
            <button
              onClick={handleDeployClick}
              disabled={deploying}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
            >
              {deploying ? "Deploying…" : "Deploy this model"}
            </button>
          )}
          {canPromoteToLive && (
            <button
              onClick={() => onPromote(projectDeployment!.id, selected.id)}
              className="rounded-lg border border-emerald-700 px-4 py-2 text-sm font-medium text-emerald-300 transition-colors hover:bg-emerald-950/40"
            >
              Promote to live deployment (v{projectDeployment!.version})
            </button>
          )}
          {selectedDeployments.map((d) => {
            // Shallow-copy in live results (from runStates) without mutating the
            // original run objects — mirrors the parentResults/tCandidates pattern above.
            const resolve = (r: Run): Run => ({ ...r, results: runStates[r.id]?.results ?? r.results });
            const currentRun = runs.find((r) => r.id === d.run_id);
            const resolvedCurrentRun = currentRun ? resolve(currentRun) : null;
            const candidates = runs
              .map(resolve)
              .filter(
                (r) =>
                  (runStates[r.id]?.status ?? r.status) === "completed" &&
                  r.plan.task_type !== "forecasting" &&
                  r.plan.target_column === d.contract.target_column &&
                  r.plan.task_type === d.contract.task_type &&
                  r.id !== d.run_id &&
                  r.results != null,
              );
            return (
              <DeploymentCard
                key={d.id}
                deployment={d}
                currentRun={resolvedCurrentRun}
                candidates={candidates}
                onPromote={async (runId) => {
                  await onPromote(d.id, runId);
                  setSelectedId(runId);
                }}
                onSetStatus={onSetStatus}
              />
            );
          })}
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
