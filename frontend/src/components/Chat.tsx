"use client";

import { Card, ChatMessage, Dataset, Methodology, Plan, Profile, Results } from "@/lib/api";
import { RunState } from "@/app/projects/[id]/page";
import ProfileCard from "./cards/ProfileCard";
import PlanCard from "./cards/PlanCard";
import TrainingCard from "./cards/TrainingCard";
import ReportCard from "./cards/ReportCard";

interface CardContext {
  datasets: Dataset[];
  methodologies: Methodology[];
  runStates: Record<string, RunState>;
  onApprove: (runId: string, overrides: Partial<Plan>) => void;
}

function CardView({ card, ctx }: { card: Card; ctx: CardContext }) {
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
    <div className="max-w-[95%] whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
      {text}
    </div>
  );
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
        <div className="max-w-[95%] whitespace-pre-wrap text-sm leading-relaxed text-zinc-200">
          {text}
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
