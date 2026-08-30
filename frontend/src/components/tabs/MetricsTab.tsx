"use client";

/**
 * Metrics tab: everything measured about the selected run.
 *
 * The full ReportCard (holdout metrics, feature importances, confusion matrix,
 * calibration, leakage checks) plus the two comparisons that only make sense
 * against other runs: retrain-vs-parent, and the N-way tournament table.
 *
 * These used to render inside the Model section, which meant a completed run
 * pushed its plan, its progress, its results, its comparisons and its
 * deployment into one column. Results earn their own surface.
 */

import { useProject } from "@/lib/project-context";
import ReportCard from "@/components/cards/ReportCard";
import ComparisonCard from "@/components/cards/ComparisonCard";
import TournamentComparisonCard, { Contender } from "@/components/cards/TournamentComparisonCard";
import EmptyTab from "@/components/tabs/EmptyTab";

export default function MetricsTab() {
  const { datasets, runs, runStates, selectedRun: selected } = useProject();

  if (!selected) {
    return (
      <section>
        <h2 className="mb-3 text-headline font-semibold text-zinc-100">Metrics</h2>
        <EmptyTab
          title="No results yet"
          body="Metrics appear once a training run finishes. Start one from the Model tab."
        />
      </section>
    );
  }

  const state = runStates[selected.id];
  const status = state?.status ?? selected.status;
  const results = state?.results ?? selected.results;
  const dataset = datasets.find((d) => d.id === selected.dataset_id);

  // Comparison vs. the run this one was retrained from (both need results).
  const parentRun = selected.parent_run_id
    ? runs.find((r) => r.id === selected.parent_run_id)
    : undefined;
  const parentResults = parentRun ? (runStates[parentRun.id]?.results ?? parentRun.results) : null;
  const parentDataset = parentRun ? datasets.find((d) => d.id === parentRun.dataset_id) : undefined;

  // Tournament siblings (candidates + ensemble) that share the selected run's
  // tournament_id and have results in — feeds the N-way comparison table.
  const tournamentContenders: Contender[] = selected.tournament_id
    ? runs
        .filter((r) => r.tournament_id === selected.tournament_id)
        .map((r) => ({ run: r, results: runStates[r.id]?.results ?? r.results }))
        .filter((c): c is Contender => !!c.results)
    : [];

  return (
    <section className="space-y-4">
      <h2 className="text-headline font-semibold text-zinc-100">Metrics</h2>

      {status !== "completed" || !results ? (
        <EmptyTab
          title={status === "failed" ? "This run failed" : "Not finished yet"}
          body={
            status === "failed"
              ? "No metrics were produced. Check the Model tab for the error, then retrain or try a different approach."
              : "Metrics appear here as soon as this run completes. Progress is on the Model tab."
          }
        />
      ) : (
        <>
          <ReportCard runId={selected.id} results={results} />

          {parentRun && parentResults && (
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
        </>
      )}
    </section>
  );
}
