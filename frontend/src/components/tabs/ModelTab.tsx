"use client";

/**
 * Model tab: what the selected run IS and what you can do to it.
 *
 * The plan awaiting approval, training progress, the reconciliation banner, and
 * the retrain/deploy/promote actions. Deliberately NOT the results — those are
 * the Metrics tab — and not the deployment detail, which is the Deploy tab.
 * Splitting them is the point of this restructure: the old single Model section
 * carried all three at once.
 *
 * Run selection is ambient (the rail's model dropdown writes `selectedRunId`),
 * so this tab reads the selection rather than owning a picker.
 */

import { useState } from "react";
import { useProject } from "@/lib/project-context";
import { findChainTip } from "@/lib/dataset-chain";
import { runLabel, isTrainingLikeStatus } from "@/lib/run-label";
import PlanCard from "@/components/cards/PlanCard";
import TournamentCard from "@/components/cards/TournamentCard";
import TrainingCard from "@/components/cards/TrainingCard";
import EmptyTab from "@/components/tabs/EmptyTab";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import { LOWER_BETTER, METRIC_LABELS, fmt } from "@/components/cards/ReportCard";

export default function ModelTab() {
  const {
    project,
    datasets,
    runs,
    deployments,
    runStates,
    methodologies,
    selectedRun: selected,
    approveRun,
    approveTournament,
    handleRetrain,
    handleDeploy,
    handlePromote,
  } = useProject();

  const [retraining, setRetraining] = useState(false);
  const [deploying, setDeploying] = useState(false);
  const [promoteDialogOpen, setPromoteDialogOpen] = useState(false);
  const [promoting, setPromoting] = useState(false);

  if (!selected) {
    return (
      <section>
        <h2 className="mb-3 text-headline font-semibold text-zinc-100">Model</h2>
        <EmptyTab
          title="No model yet"
          body="Upload a CSV on the Data tab, then tell the assistant what you want to predict. It will propose a training plan here for your approval."
        />
      </section>
    );
  }

  const state = runStates[selected.id];
  const status = state?.status ?? selected.status;
  const results = state?.results ?? selected.results;
  const dataset = datasets.find((d) => d.id === selected.dataset_id);
  const methodology = methodologies.find((m) => m.id === selected.plan.methodology_id);

  // Newer data available for the selected run's dataset chain, if any.
  const datasetTip = findChainTip(selected.dataset_id, datasets);
  const hasNewerData = !!datasetTip && datasetTip.id !== selected.dataset_id;

  // A tournament renders as a tournament for its whole life: TournamentCard in
  // place of the per-run PlanCard, showing every candidate's live status.
  //
  // This used to be gated on `tournamentPending`, so approving flipped the card
  // off and dropped the user to the single selected run. Since selection follows
  // the newest run and the ensemble is created last, that meant watching a run
  // that cannot start yet — "Waiting for tournament candidates to finish, 0%" —
  // while three candidates trained invisibly behind it. `tournamentPending` now
  // only governs the approve footer, which TournamentCard hides on its own.
  const isTournament = !!selected.tournament_id;
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
  // forecasting runs don't fit the single-record predict contract.
  const canDeploy = status === "completed" && selected.plan.task_type !== "forecasting";

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

  const projectDeploymentRun = projectDeployment
    ? (runs.find((r) => r.id === projectDeployment.run_id) ?? null)
    : null;
  const recommendedRunId = project?.recommended_run_id ?? null;
  const recommendedRun = recommendedRunId
    ? (runs.find((r) => r.id === recommendedRunId) ?? null)
    : null;
  // Two independent signals (what's live vs. what's recommended) disagreeing is a
  // state the interface must reconcile rather than leave for the user to notice.
  const needsReconciliation =
    !!projectDeployment && !!recommendedRunId && projectDeployment.run_id !== recommendedRunId;

  const projectDeploymentResults = projectDeploymentRun
    ? (runStates[projectDeploymentRun.id]?.results ?? projectDeploymentRun.results)
    : null;

  async function handleRetrainClick() {
    setRetraining(true);
    try {
      await handleRetrain(selected!.id);
    } finally {
      setRetraining(false);
    }
  }

  async function handleDeployClick() {
    setDeploying(true);
    try {
      await handleDeploy(selected!.id);
    } finally {
      setDeploying(false);
    }
  }

  async function handleConfirmPromote() {
    if (!projectDeployment) return;
    setPromoting(true);
    try {
      await handlePromote(projectDeployment.id, selected!.id);
      setPromoteDialogOpen(false);
    } finally {
      setPromoting(false);
    }
  }

  return (
    <section className="space-y-4">
      <h2 className="text-headline font-semibold text-zinc-100">Model</h2>

      {needsReconciliation && (
        <div className="measure rounded-lg border border-sky-900/60 bg-sky-950/30 px-3 py-2.5 text-label leading-relaxed text-sky-200">
          <span className="font-medium text-sky-300">
            {runLabel(projectDeploymentRun, methodologies)}
          </span>{" "}
          is currently live and serving traffic, but the assistant recommends{" "}
          <span className="font-medium text-sky-300">{runLabel(recommendedRun, methodologies)}</span>{" "}
          instead. These differ — promote the recommended run to reconcile, or leave the current
          deployment as is.
        </div>
      )}

      {selected.id === recommendedRunId && project?.recommendation_reason && (
        <div className="rounded-lg border border-emerald-900/60 bg-emerald-950/30 px-3 py-2.5">
          <div className="mb-1 text-label font-medium text-emerald-300">
            ★ Recommended by the assistant
          </div>
          <p className="measure text-label leading-relaxed text-emerald-200/80">
            {project.recommendation_reason}
          </p>
        </div>
      )}

      {isTournament ? (
        <TournamentCard
          tournamentId={selected.tournament_id!}
          datasetFilename={dataset?.filename ?? ""}
          ensemble={ensembleKind}
          candidates={tCandidates.map((r) => ({ run_id: r.id, plan: r.plan }))}
          ensembleRun={tEnsemble ? { run_id: tEnsemble.id, plan: tEnsemble.plan } : null}
          reasoning={tCandidates[0]?.plan.reasoning ?? ""}
          methodologies={methodologies}
          runStates={runStates}
          onApproveTournament={approveTournament}
        />
      ) : (
        <PlanCard
          runId={selected.id}
          datasetFilename={dataset?.filename ?? ""}
          plan={selected.plan}
          profile={dataset?.profile ?? null}
          methodologies={methodologies}
          status={status}
          onApprove={approveRun}
        />
      )}

      {!tournamentPending && isTrainingLikeStatus(status) && (
        <TrainingCard status={status} progress={state?.progress ?? null} error={state?.error ?? null} />
      )}

      {(status === "completed" && hasNewerData) ||
      (canDeploy && deployments.length === 0) ||
      canPromoteToLive ? (
        <div className="flex flex-wrap items-center gap-2">
          {status === "completed" && hasNewerData && (
            <button
              onClick={handleRetrainClick}
              disabled={retraining}
              className="focus-ring rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2 text-body font-medium text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-zinc-100 disabled:opacity-40"
            >
              {retraining ? "Retraining…" : `Retrain on updated data (v${datasetTip?.version ?? 1})`}
            </button>
          )}
          {canDeploy && deployments.length === 0 && (
            <button
              onClick={handleDeployClick}
              disabled={deploying}
              className="focus-ring rounded-lg bg-emerald-600 px-4 py-2 text-body font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
            >
              {deploying ? "Deploying…" : "Deploy this model"}
            </button>
          )}
          {canPromoteToLive && (
            <button
              onClick={() => setPromoteDialogOpen(true)}
              className="focus-ring rounded-lg bg-emerald-600 px-4 py-2 text-body font-medium text-white transition-colors hover:bg-emerald-500"
            >
              Promote to live deployment (v{projectDeployment!.version})
            </button>
          )}
        </div>
      ) : null}

      {methodology && (
        <p className="measure text-label leading-relaxed text-zinc-400">
          {methodology.display_name}: {methodology.when_to_use}
        </p>
      )}

      {canPromoteToLive && (
        <ConfirmDialog
          open={promoteDialogOpen}
          title="Promote to live deployment"
          body={
            <div className="space-y-2">
              <p>
                <span className="font-medium text-zinc-100">
                  {runLabel(projectDeploymentRun, methodologies)}
                </span>{" "}
                is serving live prediction traffic now. Confirming switches the deployment to{" "}
                <span className="font-medium text-zinc-100">
                  {runLabel(selected, methodologies)}
                </span>
                .
              </p>
              {results &&
                projectDeploymentResults &&
                results.primary_metric === projectDeploymentResults.primary_metric &&
                (() => {
                  const metric = results.primary_metric;
                  const oldValue = projectDeploymentResults.holdout.metrics[metric];
                  const newValue = results.holdout.metrics[metric];
                  if (oldValue == null || newValue == null) return null;
                  const lowerBetter = LOWER_BETTER.has(metric);
                  const delta = newValue - oldValue;
                  const improved = lowerBetter ? delta < 0 : delta > 0;
                  const deltaSign = delta > 0 ? "+" : "";
                  return (
                    <p className="text-zinc-300">
                      {METRIC_LABELS[metric] ?? metric}: {fmt(oldValue)} → {fmt(newValue)} (
                      {delta === 0
                        ? "no change"
                        : `${deltaSign}${fmt(delta)}, ${improved ? "better" : "worse"}`}
                      )
                    </p>
                  );
                })()}
              <p>
                Any caller of the existing prediction endpoint will immediately start getting
                predictions from the new model. This takes effect right away and cannot be undone
                from here.
              </p>
            </div>
          }
          confirmLabel="Promote"
          busy={promoting}
          onConfirm={handleConfirmPromote}
          onCancel={() => setPromoteDialogOpen(false)}
        />
      )}
    </section>
  );
}
