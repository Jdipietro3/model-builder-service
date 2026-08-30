import { Run } from "@/lib/api";

/**
 * One row of the model tree: either a tournament (an ensemble plus its
 * candidates, trained together) or a single standalone run. `ordinal` numbers
 * rounds V1..Vn in the order they were started, oldest first, so the number a
 * user quotes in conversation ("V2 beat V1") stays stable as new rounds arrive.
 */
export interface Round {
  key: string; // tournament_id, or the single run's id
  ordinal: number; // 1-based, V1 = oldest round
  kind: "tournament" | "single";
  runs: Run[]; // ensemble first, then candidates in creation order
  datasetId: string;
}

/**
 * Group runs into rounds and number them oldest-first, then return
 * newest-first (the order the rail renders top to bottom).
 *
 * Pure and side-effect free: the ordering rules below are meant to be
 * verifiable by reading this function, not by rendering the tree.
 */
export function groupRunsIntoRounds(runs: Run[]): Round[] {
  type Building = { key: string; kind: Round["kind"]; runs: Run[]; earliest: number };

  const byTournament = new Map<string, Building>();
  const building: Building[] = [];

  // `runs` arrives in creation order, so the first time we see a tournament_id
  // is also the earliest point to insert that round into `building` — later
  // runs from the same tournament just get appended to the group already there.
  for (const run of runs) {
    const createdAt = new Date(run.created_at).getTime();
    if (run.tournament_id) {
      const existing = byTournament.get(run.tournament_id);
      if (existing) {
        existing.runs.push(run);
        existing.earliest = Math.min(existing.earliest, createdAt);
      } else {
        const group: Building = {
          key: run.tournament_id,
          kind: "tournament",
          runs: [run],
          earliest: createdAt,
        };
        byTournament.set(run.tournament_id, group);
        building.push(group);
      }
    } else {
      building.push({ key: run.id, kind: "single", runs: [run], earliest: createdAt });
    }
  }

  // Oldest round first so `ordinal` assignment below reads naturally as V1..Vn;
  // the whole array is reversed once at the end for newest-first rendering.
  building.sort((a, b) => a.earliest - b.earliest);

  const rounds: Round[] = building.map((group, i) => {
    const orderedRuns =
      group.kind === "tournament" ? sortTournamentRuns(group.runs) : group.runs;
    return {
      key: group.key,
      ordinal: i + 1,
      kind: group.kind,
      runs: orderedRuns,
      datasetId: orderedRuns[0].dataset_id,
    };
  });

  return rounds.reverse();
}

/** Ensemble first (it's the round's headline result), then candidates in the
 *  creation order they arrived in — stable sort preserves that for ties. */
function sortTournamentRuns(runs: Run[]): Run[] {
  const ensemble = runs.filter((r) => r.tournament_role === "ensemble");
  const rest = runs
    .filter((r) => r.tournament_role !== "ensemble")
    .slice()
    .sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime());
  return [...ensemble, ...rest];
}
