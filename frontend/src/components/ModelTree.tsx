"use client";

/**
 * The rail's model picker: a two-level tree of rounds (tournaments and single
 * runs) over the runs each one produced. Replaces the old flat <select>, which
 * had no way to show that four runs belonged to one tournament versus being
 * four independent attempts.
 *
 * Plain nested <ul>/<li> with real <button>s, NOT role="tree" — a full ARIA
 * tree needs roving tabindex and arrow-key handling, and a half-built one
 * announces as a tree via the accessibility API and then doesn't behave like
 * one, which is worse for screen reader users than a plain list they already
 * know how to navigate.
 */

import { useEffect, useMemo, useRef, useState } from "react";
import { Dataset, Run } from "@/lib/api";
import { RunState, useProject } from "@/lib/project-context";
import { runLabel, STATUS_DOT } from "@/lib/run-label";
import { groupRunsIntoRounds, Round } from "@/lib/run-groups";

function statusOf(run: Run, runStates: Record<string, RunState>): string {
  return runStates[run.id]?.status ?? run.status;
}

/** A round reads as "pending" once nothing in it can be acted on yet. For a
 *  tournament that means its candidates specifically — the auto-built
 *  ensemble sits in "waiting" (not "pending_approval") until they finish, so
 *  checking every run in the round would never fire. */
function isRoundPending(round: Round, runStates: Record<string, RunState>): boolean {
  const relevant =
    round.kind === "tournament"
      ? round.runs.filter((r) => r.tournament_role === "candidate")
      : round.runs;
  return relevant.length > 0 && relevant.every((r) => statusOf(r, runStates) === "pending_approval");
}

/**
 * The data version is shown ONLY when the project has rounds on more than one
 * dataset version.
 *
 * Measured at the rail's width, "Tournament · data v1" overflows and `truncate`
 * eats the tail — which is the data version, the half that carries meaning.
 * Rather than fight for the space, drop the qualifier when every round sits on
 * the same data, where it distinguishes nothing and is pure noise repeated down
 * the rail. It reappears the moment a retrain puts a round on newer data, which
 * is the only time a reader needs it.
 */
function roundSubtitle(round: Round, dataset: Dataset | undefined, showData: boolean): string {
  const kind = round.kind === "single" ? "Single model" : "Tournament";
  if (!showData || dataset?.version == null) return kind;
  return `${kind} · data v${dataset.version}`;
}

export default function ModelTree() {
  const { runs, selectedRunId, setSelectedRunId, runStates, methodologies, deployments, datasets } =
    useProject();

  const rounds = useMemo(() => groupRunsIntoRounds(runs), [runs]);
  const liveRunId = deployments[0]?.run_id ?? null;
  const showDataVersion = new Set(rounds.map((r) => r.datasetId)).size > 1;

  const selectedRoundKey =
    rounds.find((round) => round.runs.some((r) => r.id === selectedRunId))?.key ?? null;

  // A round with no entry here falls back to "expanded iff it holds the
  // selection" (see isExpanded), so a manual toggle persists across re-renders
  // without being clobbered — but when the selection jumps into a *different*
  // round (a freshly proposed tournament auto-follows the selection), force
  // that round open even if the user had previously collapsed it.
  const [manualExpanded, setManualExpanded] = useState<Record<string, boolean>>({});
  const lastRoundKeyRef = useRef<string | null>(null);
  useEffect(() => {
    if (selectedRoundKey && selectedRoundKey !== lastRoundKeyRef.current) {
      lastRoundKeyRef.current = selectedRoundKey;
      setManualExpanded((prev) => ({ ...prev, [selectedRoundKey]: true }));
    }
  }, [selectedRoundKey]);

  function isExpanded(round: Round): boolean {
    return manualExpanded[round.key] ?? round.key === selectedRoundKey;
  }

  return (
    <div>
      <h2
        id="model-tree-heading"
        className="mb-1.5 px-1 text-label uppercase tracking-wide text-zinc-400"
      >
        Model
      </h2>

      {rounds.length === 0 ? (
        <p className="px-1 text-label text-zinc-400">None yet</p>
      ) : (
        <ul aria-labelledby="model-tree-heading" className="space-y-0.5">
          {rounds.map((round) => {
            const expanded = isExpanded(round);
            const dataset = datasets.find((d) => d.id === round.datasetId);
            const pending = isRoundPending(round, runStates);
            return (
              <li key={round.key}>
                <button
                  type="button"
                  aria-expanded={expanded}
                  onClick={() => setManualExpanded((prev) => ({ ...prev, [round.key]: !expanded }))}
                  className="focus-ring-panel flex w-full items-center justify-between gap-2 rounded px-2 py-1.5 text-left transition-colors hover:bg-zinc-900"
                >
                  <span className="flex min-w-0 items-baseline gap-1.5">
                    <span className="shrink-0 text-label font-semibold text-zinc-200">
                      V{round.ordinal}
                    </span>
                    <span className="truncate text-label text-zinc-400" title={roundSubtitle(round, dataset, showDataVersion)}>
                      {roundSubtitle(round, dataset, showDataVersion)}
                    </span>
                  </span>
                  <span className="flex shrink-0 items-center gap-1.5">
                    {pending && (
                      <span className="rounded bg-amber-950 px-1.5 py-0.5 text-label font-medium text-amber-300">
                        pending
                      </span>
                    )}
                    <span aria-hidden="true" className="text-label text-zinc-400">
                      {expanded ? "▾" : "▸"}
                    </span>
                  </span>
                </button>

                {expanded && (
                  <ul className="mt-0.5 space-y-0.5 pl-3">
                    {round.runs.map((run) => {
                      const status = statusOf(run, runStates);
                      const selected = run.id === selectedRunId;
                      const live = run.id === liveRunId;
                      return (
                        <li key={run.id}>
                          <button
                            type="button"
                            onClick={() => setSelectedRunId(run.id)}
                            aria-current={selected ? "true" : undefined}
                            className={`focus-ring-panel flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-body transition-colors ${
                              selected
                                ? "bg-zinc-900 text-zinc-100"
                                : "text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100"
                            }`}
                          >
                            <span
                              aria-hidden="true"
                              className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                                STATUS_DOT[status] ?? "bg-zinc-500"
                              }`}
                            />
                            <span className="min-w-0 flex-1 truncate" title={runLabel(run, methodologies)}>
                              {runLabel(run, methodologies)}
                            </span>
                            {live && (
                              <span className="shrink-0 rounded bg-emerald-950 px-1.5 py-0.5 text-label font-medium text-emerald-400">
                                live
                              </span>
                            )}
                          </button>
                        </li>
                      );
                    })}
                  </ul>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
