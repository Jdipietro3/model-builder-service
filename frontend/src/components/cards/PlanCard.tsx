"use client";

import { useMemo, useState } from "react";
import { Methodology, Plan, Profile } from "@/lib/api";
import Disclosure from "@/components/Disclosure";

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  pending_approval: { label: "Awaiting approval", cls: "bg-accent-wash text-accent" },
  queued: { label: "Queued", cls: "bg-info-wash text-info" },
  running: { label: "Training", cls: "bg-info-wash text-info" },
  completed: { label: "Completed", cls: "bg-zinc-800 text-zinc-400" },
  failed: { label: "Failed", cls: "bg-alarm-wash text-alarm" },
};

export default function PlanCard({
  runId,
  datasetFilename,
  plan,
  profile,
  methodologies,
  status,
  onApprove,
  variant = "card",
}: {
  runId: string;
  datasetFilename: string;
  plan: Plan;
  profile: Profile | null;
  methodologies: Methodology[];
  status: string;
  onApprove: (runId: string, overrides: Partial<Plan>) => void;
  variant?: "card" | "band";
}) {
  const isForecasting = plan.task_type === "forecasting";

  const [target, setTarget] = useState(plan.target_column);
  const [methodologyId, setMethodologyId] = useState(plan.methodology_id);
  const [metric, setMetric] = useState(plan.primary_metric);
  const [excluded, setExcluded] = useState<string[]>(plan.excluded_columns);
  const [timeColumn, setTimeColumn] = useState(plan.time_column ?? "");
  const [horizon, setHorizon] = useState(plan.horizon ?? 1);

  const editable = status === "pending_approval";
  const columns = profile?.columns.map((c) => c.name) ?? [plan.target_column];

  // Time-column candidates: datetime-kind columns; fall back to all columns if
  // none are marked (older profiles or ambiguous data).
  const datetimeColumns =
    profile?.columns.filter((c) => c.kind === "datetime").map((c) => c.name) ?? [];
  const timeColumnOptions = datetimeColumns.length > 0 ? [...datetimeColumns] : [...columns];
  if (timeColumn && !timeColumnOptions.includes(timeColumn)) timeColumnOptions.unshift(timeColumn);
  const compatible = useMemo(
    () =>
      methodologies.filter(
        (m) => m.task_types.includes(plan.task_type) && m.task_family !== "ensemble",
      ),
    [methodologies, plan.task_type],
  );
  const chosen = compatible.find((m) => m.id === methodologyId);
  const supportedMetrics = chosen?.metrics[plan.task_type]?.supported ?? [metric];

  function pickMethodology(id: string) {
    setMethodologyId(id);
    const m = compatible.find((x) => x.id === id);
    const def = m?.metrics[plan.task_type]?.default;
    if (def) setMetric(def);
  }

  const badge = STATUS_LABELS[status] ?? STATUS_LABELS.pending_approval;
  const selectCls =
    "focus-ring-panel w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-body text-zinc-200 focus:border-accent-edge disabled:cursor-default disabled:border-transparent disabled:appearance-none disabled:px-0";
  const isBand = variant === "band";
  const sidePad = isBand ? "" : "px-4";

  return (
    <div className={isBand ? "" : "overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900/80"}>
      <div className={`flex items-center justify-between border-b border-zinc-800 py-3 ${sidePad}`}>
        <div className="flex items-center gap-2">
          {isBand ? (
            <span className="text-title font-medium text-zinc-100">Training plan</span>
          ) : (
            <span className="rounded bg-zinc-800 px-2 py-0.5 text-label font-medium text-zinc-400">
              TRAINING PLAN
            </span>
          )}
          <span className="text-label text-zinc-400">on {datasetFilename}</span>
        </div>
        <span className={`rounded px-2 py-0.5 text-label font-medium ${badge.cls}`}>
          {badge.label}
        </span>
      </div>

      <div className={`py-3 ${sidePad}`}>
        {/* Open while the run is awaiting approval — these selects are the
            thing the user must act on. Once a run has moved past that, the
            plan is fixed and this becomes reference, so it starts closed. */}
        <Disclosure
          summary="Plan summary"
          meta={`${plan.task_type.replace(/_/g, " ")} · ${chosen?.display_name ?? methodologyId}`}
          defaultOpen={editable}
        >
          <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            <div>
              <div className="mb-1 text-label text-zinc-400">Task</div>
              <div className="text-body text-zinc-200">{plan.task_type.replace(/_/g, " ")}</div>
            </div>
            <div>
              <div className="mb-1 text-label text-zinc-400">Target column</div>
              <select
                value={target}
                onChange={(e) => setTarget(e.target.value)}
                disabled={!editable}
                className={selectCls}
              >
                {columns.map((c) => (
                  <option key={c} value={c}>
                    {c}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className="mb-1 text-label text-zinc-400">Methodology</div>
              <select
                value={methodologyId}
                onChange={(e) => pickMethodology(e.target.value)}
                disabled={!editable}
                className={selectCls}
              >
                {compatible.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.display_name}
                  </option>
                ))}
              </select>
            </div>
            <div>
              <div className="mb-1 text-label text-zinc-400">Optimize for</div>
              <select
                value={metric}
                onChange={(e) => setMetric(e.target.value)}
                disabled={!editable}
                className={selectCls}
              >
                {supportedMetrics.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </div>
            {isForecasting && (
              <div>
                <div className="mb-1 text-label text-zinc-400">Time column</div>
                <select
                  value={timeColumn}
                  onChange={(e) => setTimeColumn(e.target.value)}
                  disabled={!editable}
                  className={selectCls}
                >
                  {timeColumnOptions.map((c) => (
                    <option key={c} value={c}>
                      {c}
                    </option>
                  ))}
                </select>
              </div>
            )}
            {isForecasting && (
              <div>
                <div className="mb-1 text-label text-zinc-400">Horizon (periods to forecast)</div>
                <input
                  type="number"
                  min={1}
                  value={horizon}
                  onChange={(e) => {
                    const v = parseInt(e.target.value, 10);
                    setHorizon(Number.isNaN(v) ? 1 : Math.max(1, v));
                  }}
                  disabled={!editable}
                  className={selectCls}
                />
              </div>
            )}
          </div>
        </Disclosure>
      </div>

      <div className={`pb-3 ${sidePad}`}>
        <Disclosure summary="Excluded columns" meta={`${excluded.length}`} tone="label">
          {profile && (
            <div className="flex flex-wrap gap-1.5">
              {profile.columns
                .filter((c) => c.name !== target)
                .map((c) => {
                  const isExcluded = excluded.includes(c.name);
                  return (
                    <button
                      key={c.name}
                      disabled={!editable}
                      onClick={() =>
                        setExcluded((prev) =>
                          isExcluded ? prev.filter((x) => x !== c.name) : [...prev, c.name],
                        )
                      }
                      className={`focus-ring-panel rounded-full border px-2.5 py-0.5 font-mono text-xs transition-colors ${
                        isExcluded
                          ? "border-alarm/40 bg-alarm-wash text-alarm line-through"
                          : "border-zinc-700 text-zinc-400"
                      } ${editable ? "hover:border-zinc-500" : "cursor-default"}`}
                    >
                      {c.name}
                    </button>
                  );
                })}
              <p className="mt-1 w-full text-label text-zinc-400">
                Click to toggle. Excluded columns are not used as features.
              </p>
            </div>
          )}
        </Disclosure>
      </div>

      {plan.warnings && plan.warnings.length > 0 && (
        <div className={`border-t border-zinc-800 py-3 ${sidePad}`}>
          {/* Closed by default — this is the worst offender for page length,
              rendering one chip per affected column across every warning. */}
          <Disclosure summary="Warnings" meta={`${plan.warnings.length} findings`}>
            <div className="space-y-2.5">
              {plan.warnings.map((w, i) => {
                const high = w.severity === "high";
                return (
                  <div key={i} className="flex items-start gap-2">
                    <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-alarm" />
                    <div className="measure">
                      <div className="text-label font-medium text-zinc-100">
                        {high ? "High risk" : "Worth checking"} · {w.category.replace(/_/g, " ")}
                      </div>
                      <p className="text-label leading-relaxed text-zinc-300">{w.message}</p>
                      {w.columns.length > 0 && (
                        <div className="mt-1.5 flex flex-wrap gap-1">
                          {w.columns.map((c) => (
                            <span
                              key={c}
                              className="rounded-full border border-zinc-700 px-2 py-0.5 font-mono text-xs text-zinc-400"
                            >
                              {c}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          </Disclosure>
        </div>
      )}

      {plan.reasoning && (
        <div className={`border-t border-zinc-800 py-3 ${sidePad}`}>
          <div className="border-l-2 border-accent-line pl-3">
            <div className="mb-1 text-label font-medium text-accent">Why this plan</div>
            <p className="measure text-body leading-relaxed text-zinc-200">{plan.reasoning}</p>
          </div>
        </div>
      )}

      {editable && (
        <div
          className={`flex items-center justify-between border-t border-zinc-800 py-3 ${sidePad} ${
            isBand ? "" : "bg-zinc-900"
          }`}
        >
          <span className="text-label text-zinc-400">
            {isForecasting
              ? `${plan.validation.n_splits} validation folds (rolling-origin backtest) + holdout window`
              : `${plan.validation.n_splits}-fold cross-validation + 20% holdout`}
          </span>
          <button
            onClick={() =>
              onApprove(runId, {
                target_column: target,
                methodology_id: methodologyId,
                primary_metric: metric,
                excluded_columns: excluded,
                ...(isForecasting ? { time_column: timeColumn || null, horizon } : {}),
              })
            }
            className="focus-ring-panel rounded-lg bg-accent px-5 py-2 text-body font-medium text-accent-ink transition-colors hover:bg-accent-bright"
          >
            Approve &amp; train
          </button>
        </div>
      )}
    </div>
  );
}
