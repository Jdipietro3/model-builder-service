import { Methodology, Run } from "@/lib/api";

/** Human label for a run: its methodology's display name, falling back to
 *  "Ensemble" for an auto-built tournament ensemble and finally to the raw id.
 *  Lifted out of Workspace so the rail's model dropdown and the tabs agree. */
export function runLabel(r: Run | null | undefined, methodologies: Methodology[]): string {
  if (!r) return "an earlier model";
  const m = methodologies.find((x) => x.id === r.plan.methodology_id);
  return m?.display_name ?? (r.tournament_role === "ensemble" ? "Ensemble" : r.plan.methodology_id);
}

/** Lifecycle dot colours, shared by the rail and the tabs.
 *
 *  Both consumers interpolate the value straight into a className, so an entry
 *  may carry more than one utility — `running` pairs its hue with the pulse.
 *
 *  Note `completed` is deliberately the quietest entry rather than the loudest.
 *  It used to be emerald, back when emerald was the accent, which meant the
 *  single most common state on the screen was also the most eye-catching thing
 *  on it. Almost every run completes; if that state wears the accent it spends
 *  the whole accent budget on the resting case and the dot stops signalling
 *  anything. The states worth looking at are the ones that are coloured now:
 *  something needs your approval, something is moving, something broke. */
export const STATUS_DOT: Record<string, string> = {
  pending_approval: "bg-accent", // awaiting your decision — the one call to action
  queued: "bg-zinc-600",
  running: "bg-info animate-pulse",
  waiting: "bg-zinc-600",
  claimed: "bg-zinc-600", // transient promotion-mutex state; treated like waiting
  completed: "bg-zinc-400",
  failed: "bg-alarm",
};

/** Statuses that mean "still working toward a result" for TrainingCard purposes,
 *  including the ensemble's pre-promotion "waiting" state (and the brief
 *  "claimed" state seen during promotion). */
export function isTrainingLikeStatus(status: string): boolean {
  return ["queued", "running", "failed", "waiting", "claimed"].includes(status);
}
