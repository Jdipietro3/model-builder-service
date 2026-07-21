"use client";

import { Card, ChatMessage, Dataset, Methodology, Plan, Profile, Results } from "@/lib/api";
import { RunState } from "@/app/projects/[id]/page";
import Markdown from "./Markdown";
import ProfileCard from "./cards/ProfileCard";
import PlanCard from "./cards/PlanCard";
import TrainingCard from "./cards/TrainingCard";
import ReportCard from "./cards/ReportCard";
import TournamentCard from "./cards/TournamentCard";

interface CardContext {
  datasets: Dataset[];
  methodologies: Methodology[];
  runStates: Record<string, RunState>;
  onApprove: (runId: string, overrides: Partial<Plan>) => void;
  onApproveTournament: (tournamentId: string) => void;
  /** Rail mode: cards render as small reference chips instead of full cards. */
  compact?: boolean;
}

const CHIP_LABELS: Record<string, (card: Card) => string> = {
  profile: (c) => `Dataset profiled: ${c.filename}`,
  plan: () => "Training plan proposed",
  report: () => "Training results ready",
  dataset_update: (c) => {
    const diff = c.diff as { rows_added?: number } | undefined;
    const rows = diff?.rows_added;
    const sign = typeof rows === "number" && rows > 0 ? "+" : "";
    return `Data updated → v${c.version} (${sign}${rows ?? 0} rows)`;
  },
  retrain: () => "Retraining on updated data",
  tournament: () => "Tournament proposed",
};

function CardChip({ card }: { card: Card }) {
  const label = CHIP_LABELS[card.type]?.(card) ?? card.type;
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-zinc-800 bg-zinc-900 px-3 py-1 text-xs text-zinc-400">
      <span className="h-1.5 w-1.5 rounded-full bg-sky-400" />
      {label} — see workspace
    </span>
  );
}

function CardView({ card, ctx }: { card: Card; ctx: CardContext }) {
  if (ctx.compact) {
    return <CardChip card={card} />;
  }

  if (card.type === "profile") {
    return (
      <ProfileCard
        filename={card.filename as string}
        profile={card.profile as Profile}
      />
    );
  }

  if (card.type === "plan") {
    const runId = card.run_id as string;
    const state = ctx.runStates[runId];
    const dataset = ctx.datasets.find((d) => d.id === (card.dataset_id as string));
    return (
      <div className="space-y-3">
        <PlanCard
          runId={runId}
          datasetFilename={card.dataset_filename as string}
          plan={card.plan as Plan}
          profile={dataset?.profile ?? null}
          methodologies={ctx.methodologies}
          status={state?.status ?? "pending_approval"}
          onApprove={ctx.onApprove}
        />
        {state && ["queued", "running", "failed"].includes(state.status) && (
          <TrainingCard status={state.status} progress={state.progress} error={state.error} />
        )}
        {state && state.status === "completed" && state.live && state.results && (
          <ReportCard runId={runId} results={state.results} />
        )}
      </div>
    );
  }

  if (card.type === "report") {
    return <ReportCard runId={card.run_id as string} results={card.results as Results} />;
  }

  if (card.type === "dataset_update") {
    const diff = card.diff as
      | { rows_before: number; rows_after: number; rows_added: number }
      | undefined;
    return (
      <div className="space-y-2">
        {diff && (
          <p className="text-xs text-zinc-500">
            Dataset updated to v{card.version as number}: {diff.rows_before.toLocaleString()} →{" "}
            {diff.rows_after.toLocaleString()} rows ({diff.rows_added >= 0 ? "+" : ""}
            {diff.rows_added})
          </p>
        )}
        <ProfileCard filename={card.filename as string} profile={card.profile as Profile} />
      </div>
    );
  }

  if (card.type === "retrain") {
    return (
      <p className="text-sm text-zinc-400">
        Retraining on updated data — see workspace for progress.
      </p>
    );
  }

  if (card.type === "tournament") {
    return (
      <TournamentCard
        tournamentId={card.tournament_id as string}
        datasetFilename={card.dataset_filename as string}
        ensemble={card.ensemble as "blend" | "stacking" | "none"}
        candidates={card.candidates as { run_id: string; plan: Plan }[]}
        ensembleRun={card.ensemble_run as { run_id: string; plan: Plan } | null}
        reasoning={card.reasoning as string}
        methodologies={ctx.methodologies}
        runStates={ctx.runStates}
        onApproveTournament={ctx.onApproveTournament}
      />
    );
  }

  return null;
}

function Bubble({ role, text }: { role: string; text: string }) {
  if (!text) return null;
  if (role === "user") {
    return (
      <div className="flex justify-end">
        <div className="max-w-[85%] whitespace-pre-wrap rounded-2xl rounded-br-sm bg-emerald-900/40 px-4 py-2.5 text-sm leading-relaxed text-emerald-50">
          {text}
        </div>
      </div>
    );
  }
  return (
    <div className="max-w-[95%] text-sm leading-relaxed text-zinc-200">
      <Markdown text={text} />
    </div>
  );
}

/** Close an unterminated ``` fence so partial streams render as code, not prose. */
function closeOpenFence(text: string): string {
  const fences = (text.match(/```/g) ?? []).length;
  return fences % 2 === 1 ? text + "\n```" : text;
}

export function MessageView({
  message,
  ...ctx
}: { message: ChatMessage } & CardContext) {
  return (
    <div className="space-y-3">
      <Bubble role={message.role} text={message.content} />
      {message.cards?.map((card, i) => (
        <CardView key={i} card={card} ctx={ctx} />
      ))}
    </div>
  );
}

export function StreamingMessage({
  text,
  cards,
  ...ctx
}: { text: string; cards: Card[] } & CardContext) {
  return (
    <div className="space-y-3">
      {text ? (
        <div className="max-w-[95%] text-sm leading-relaxed text-zinc-200">
          <Markdown text={closeOpenFence(text)} />
          <span className="ml-0.5 inline-block h-4 w-2 animate-pulse bg-emerald-500 align-text-bottom" />
        </div>
      ) : (
        <div className="flex items-center gap-2 text-sm text-zinc-500">
          <span className="h-2 w-2 animate-pulse rounded-full bg-emerald-500" />
          Thinking…
        </div>
      )}
      {cards.map((card, i) => (
        <CardView key={i} card={card} ctx={ctx} />
      ))}
    </div>
  );
}
