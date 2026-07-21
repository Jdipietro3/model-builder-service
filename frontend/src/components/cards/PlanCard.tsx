"use client";

import { useMemo, useState } from "react";
import { Methodology, Plan, Profile } from "@/lib/api";

const STATUS_LABELS: Record<string, { label: string; cls: string }> = {
  pending_approval: { label: "Awaiting approval", cls: "bg-amber-950 text-amber-300" },
  queued: { label: "Queued", cls: "bg-sky-950 text-sky-300" },
  running: { label: "Training", cls: "bg-sky-950 text-sky-300" },
  completed: { label: "Completed", cls: "bg-emerald-950 text-emerald-300" },
  failed: { label: "Failed", cls: "bg-red-950 text-red-300" },
};

export default function PlanCard({
  runId,
  datasetFilename,
  plan,
  profile,
  methodologies,
  status,
  onApprove,
}: {
  runId: string;
  datasetFilename: string;
  plan: Plan;
  profile: Profile | null;
  methodologies: Methodology[];
  status: string;
  onApprove: (runId: string, overrides: Partial<Plan>) => void;
}) {
  const isForecasting = plan.task_type === "forecasting";

  const [target, setTarget] = useState(plan.target_column);
  const [methodologyId, setMethodologyId] = useState(plan.methodology_id);
  const [metric, setMetric] = useState(plan.primary_metric);
  const [excluded, setExcluded] = useState<string[]>(plan.excluded_columns);
  const [showExclusions, setShowExclusions] = useState(false);
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
    "w-full rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-sm text-zinc-200 outline-none focus:border-emerald-600 disabled:cursor-default disabled:border-transparent disabled:appearance-none disabled:px-0";

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900/80">
      <div className="flex items-center justify-between border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-violet-950 px-2 py-0.5 text-xs font-medium text-violet-300">
            TRAINING PLAN
          </span>
          <span className="text-xs text-zinc-500">on {datasetFilename}</span>
        </div>
        <span className={`rounded px-2 py-0.5 text-xs font-medium ${badge.cls}`}>
          {badge.label}
        </span>
      </div>

      <div className="grid grid-cols-2 gap-x-6 gap-y-3 px-4 py-4 sm:grid-cols-4">
        <div>
          <div className="mb-1 text-xs text-zinc-500">Task</div>
          <div className="text-sm text-zinc-200">{plan.task_type.replace(/_/g, " ")}</div>
        </div>
        <div>
          <div className="mb-1 text-xs text-zinc-500">Target column</div>
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
          <div className="mb-1 text-xs text-zinc-500">Methodology</div>
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
          <div className="mb-1 text-xs text-zinc-500">Optimize for</div>
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
            <div className="mb-1 text-xs text-zinc-500">Time column</div>
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
            <div className="mb-1 text-xs text-zinc-500">Horizon (periods to forecast)</div>
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

      <div className="px-4 pb-3">
        <button
          onClick={() => setShowExclusions(!showExclusions)}
          className="text-xs text-zinc-500 transition-colors hover:text-zinc-300"
        >
          {showExclusions ? "▾" : "▸"} Excluded columns ({excluded.length})
        </button>
        {showExclusions && profile && (
          <div className="mt-2 flex flex-wrap gap-1.5">
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
                    className={`rounded-full border px-2.5 py-0.5 font-mono text-xs transition-colors ${
                      isExcluded
                        ? "border-red-900 bg-red-950/60 text-red-300 line-through"
                        : "border-zinc-700 text-zinc-400"
                    } ${editable ? "hover:border-zinc-500" : "cursor-default"}`}
                  >
                    {c.name}
                  </button>
                );
              })}
            <p className="mt-1 w-full text-[11px] text-zinc-600">
              Click to toggle. Excluded columns are not used as features.
            </p>
          </div>
        )}
      </div>

      {plan.warnings && plan.warnings.length > 0 && (
        <div className="border-t border-zinc-800 px-4 py-3">
          <div className="space-y-2">
            {plan.warnings.map((w, i) => {
              const high = w.severity === "high";
              return (
                <div
                  key={i}
                  className={`rounded-lg border px-3 py-2.5 ${
                    high
                      ? "border-red-900/70 bg-red-950/30"
                      : "border-amber-900/60 bg-amber-950/30"
                  }`}
                >
                  <div
                    className={`mb-1 text-xs font-medium ${
                      high ? "text-red-300" : "text-amber-300"
                    }`}
                  >
                    {high ? "High risk" : "Worth checking"} · {w.category.replace(/_/g, " ")}
                  </div>
                  <p
                    className={`text-xs leading-relaxed ${
                      high ? "text-red-200/80" : "text-amber-200/80"
                    }`}
                  >
                    {w.message}
                  </p>
                  {w.columns.length > 0 && (
                    <div className="mt-1.5 flex flex-wrap gap-1">
                      {w.columns.map((c) => (
                        <span
                          key={c}
                          className={`rounded-full border px-2 py-0.5 font-mono text-[11px] ${
                            high
                              ? "border-red-900 text-red-300"
                              : "border-amber-900 text-amber-300"
                          }`}
                        >
                          {c}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        </div>
      )}

      {plan.reasoning && (
        <div className="border-t border-zinc-800 px-4 py-3">
          <div className="mb-1 text-xs font-medium text-zinc-500">Why this plan</div>
          <p className="text-sm leading-relaxed text-zinc-400">{plan.reasoning}</p>
        </div>
      )}

      {editable && (
        <div className="flex items-center justify-between border-t border-zinc-800 bg-zinc-900 px-4 py-3">
          <span className="text-xs text-zinc-500">
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
            className="rounded-lg bg-emerald-600 px-5 py-2 text-sm font-medium text-white transition-colors hover:bg-emerald-500"
          >
            Approve &amp; train
          </button>
        </div>
      )}
    </div>
  );
}
