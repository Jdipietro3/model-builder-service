import { Methodology, Run } from "@/lib/api";

/** Human label for a run: its methodology's display name, falling back to
 *  "Ensemble" for an auto-built tournament ensemble and finally to the raw id.
 *  Lifted out of Workspace so the rail's model dropdown and the tabs agree. */
export function runLabel(r: Run | null | undefined, methodologies: Methodology[]): string {
  if (!r) return "an earlier model";
  const m = methodologies.find((x) => x.id === r.plan.methodology_id);
  return m?.display_name ?? (r.tournament_role === "ensemble" ? "Ensemble" : r.plan.methodology_id);
}

/** Lifecycle dot colours, shared by the rail and the tabs. */
export const STATUS_DOT: Record<string, string> = {
  pending_approval: "bg-amber-400",
  queued: "bg-sky-400",
  running: "bg-sky-400",
  waiting: "bg-zinc-500",
  claimed: "bg-zinc-500", // transient promotion-mutex state; treated like waiting
  completed: "bg-emerald-500",
  failed: "bg-red-500",
};

/** Statuses that mean "still working toward a result" for TrainingCard purposes,
 *  including the ensemble's pre-promotion "waiting" state (and the brief
 *  "claimed" state seen during promotion). */
export function isTrainingLikeStatus(status: string): boolean {
  return ["queued", "running", "failed", "waiting", "claimed"].includes(status);
}
