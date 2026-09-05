"use client";

import { Methodology, Plan } from "@/lib/api";
import { RunState } from "@/lib/project-context";

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  pending_approval: { label: "Awaiting approval", cls: "bg-accent-wash text-accent" },
  queued: { label: "Queued", cls: "bg-info-wash text-info" },
  running: { label: "Training", cls: "bg-info-wash text-info" },
  waiting: { label: "Waiting", cls: "bg-zinc-800 text-zinc-400" },
  claimed: { label: "Waiting", cls: "bg-zinc-800 text-zinc-400" },
  completed: { label: "Completed", cls: "bg-zinc-800 text-zinc-400" },
  failed: { label: "Failed", cls: "bg-alarm-wash text-alarm" },
};

const STATUS_DOT: Record<string, string> = {
  pending_approval: "bg-accent",
  queued: "bg-info",
  running: "bg-info",
  waiting: "bg-zinc-600",
  claimed: "bg-zinc-600",
  completed: "bg-zinc-400",
  failed: "bg-alarm",
};

interface TournamentCandidate {
  run_id: string;
  plan: Plan;
}

export default function TournamentCard({
  tournamentId,
  datasetFilename,
  ensemble,
  candidates,
  ensembleRun,
  reasoning,
  methodologies,
  runStates,
  onApproveTournament,
}: {
  tournamentId: string;
  datasetFilename: string;
  ensemble: "blend" | "stacking" | "none";
  candidates: TournamentCandidate[];
  ensembleRun: TournamentCandidate | null;
  reasoning: string;
  methodologies: Methodology[];
  runStates: Record<string, RunState>;
  onApproveTournament: (tournamentId: string) => void;
}) {
  const shared = candidates[0]?.plan;
  const allPending = candidates.every(
    (c) => (runStates[c.run_id]?.status ?? "pending_approval") === "pending_approval",
  );

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900/80">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-bracket-wash px-2 py-0.5 text-xs font-medium text-bracket">
            TOURNAMENT
          </span>
          <span className="text-xs text-zinc-400">on {datasetFilename}</span>
        </div>
      </div>

      {shared && (
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 px-4 py-4 sm:grid-cols-4">
          <div>
            <div className="mb-1 text-xs text-zinc-400">Task</div>
            <div className="text-sm text-zinc-200">{shared.task_type.replace(/_/g, " ")}</div>
          </div>
          <div>
            <div className="mb-1 text-xs text-zinc-400">Target column</div>
            <div className="text-sm text-zinc-200">{shared.target_column}</div>
          </div>
          <div>
            <div className="mb-1 text-xs text-zinc-400">Optimize for</div>
            <div className="text-sm text-zinc-200">{shared.primary_metric}</div>
          </div>
          <div>
            <div className="mb-1 text-xs text-zinc-400">Candidates</div>
            <div className="text-sm text-zinc-200">{candidates.length}</div>
          </div>
        </div>
      )}

      <div className="space-y-1.5 px-4 pb-3">
        {candidates.map((c) => {
          const status = runStates[c.run_id]?.status ?? "pending_approval";
          const badge = STATUS_LABELS[status] ?? STATUS_LABELS.pending_approval;
          const dot = STATUS_DOT[status] ?? "bg-zinc-500";
          const methodology = methodologies.find((m) => m.id === c.plan.methodology_id);
          return (
            <div
              key={c.run_id}
              className="flex items-center justify-between rounded-lg bg-zinc-800/40 px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <span className={`h-1.5 w-1.5 rounded-full ${dot}`} />
                <span className="text-sm text-zinc-200">
                  {methodology?.display_name ?? c.plan.methodology_id}
                </span>
              </div>
              <span className={`rounded px-2 py-0.5 text-xs font-medium ${badge.cls}`}>
                {badge.label}
              </span>
            </div>
          );
        })}

        {ensemble !== "none" && (
          <div className="flex items-center justify-between rounded-lg bg-bracket-wash px-3 py-2">
            <div className="flex items-center gap-2">
              <span className="h-1.5 w-1.5 rounded-full bg-bracket" />
              <span className="text-sm text-zinc-300">
                Auto-build {ensemble === "blend" ? "weighted blend" : "stacked"} ensemble from
                whichever candidates complete
              </span>
            </div>
            {ensembleRun && (
              <span className="rounded bg-zinc-800 px-2 py-0.5 text-xs font-medium text-zinc-400">
                {STATUS_LABELS[runStates[ensembleRun.run_id]?.status ?? "waiting"]?.label ??
                  "Waiting"}
              </span>
            )}
          </div>
        )}
      </div>

      {reasoning && (
        <div className="border-t border-zinc-800 px-4 py-3">
          <div className="mb-1 text-xs font-medium text-zinc-400">Why this tournament</div>
          <p className="measure text-sm leading-relaxed text-zinc-400">{reasoning}</p>
        </div>
      )}

      {allPending && (
        <div className="flex items-center justify-between border-t border-zinc-800 bg-zinc-900 px-4 py-3">
          <span className="text-xs text-zinc-400">
            {candidates.length}-way champion/challenger
            {ensemble !== "none" ? " + auto-ensemble" : ""}
          </span>
          <button
            onClick={() => onApproveTournament(tournamentId)}
            className="focus-ring-panel rounded-lg bg-accent px-5 py-2 text-sm font-medium text-accent-ink transition-colors hover:bg-accent-bright"
          >
            Approve &amp; train all
          </button>
        </div>
      )}
    </div>
  );
}
