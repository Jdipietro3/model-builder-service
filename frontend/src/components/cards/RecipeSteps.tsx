"use client";

// Shared rendering for a preprocessing/feature-engineering recipe — used by
// both PlanCard (editable, pre-approval) and ReportCard (read-only, applied).

const OP_LABELS: Record<string, string> = {
  drop: "Drop column",
  impute: "Impute missing values",
  scale: "Scale",
  encode: "Encode",
  datetime_expand: "Expand datetimes",
  log_transform: "Log transform",
  power: "Power transform",
  clip_outliers: "Clip outliers",
  bin: "Bin",
  arithmetic: "Arithmetic combination",
  interactions: "Feature interactions",
  group_aggregate: "Group aggregate",
  select: "Select features",
  class_balance: "Balance classes",
  target_transform: "Transform target",
};

/** Humanize an op name for ops the server introduces later that this build doesn't know about yet. */
export function humanizeOp(op: string): string {
  return OP_LABELS[op] ?? op.replace(/_/g, " ").replace(/^./, (c) => c.toUpperCase());
}

// Ops the server always needs to produce a working model — never user-removable.
export const REQUIRED_OPS = new Set(["impute", "encode"]);

export function ColumnChip({ children }: { children: string }) {
  return (
    <span className="rounded-full border border-zinc-700 px-2 py-0.5 font-mono text-xs text-zinc-400">
      {children}
    </span>
  );
}

export interface StepLike {
  op: string;
  columns: string[];
  params: Record<string, unknown>;
  description?: string | null;
}

/**
 * One recipe step row: index, humanized op label, description, column chips.
 * `removed` renders a greyed/line-through state (PlanCard only). `onToggleRemove`
 * present + step op not in REQUIRED_OPS shows the × control.
 */
export function RecipeStepRow({
  index,
  step,
  removed,
  removable,
  onToggleRemove,
}: {
  index: number;
  step: StepLike;
  removed?: boolean;
  removable?: boolean;
  onToggleRemove?: () => void;
}) {
  return (
    <div
      className={`flex items-start gap-2.5 rounded-md px-2.5 py-2 ${
        removed ? "bg-zinc-950/40" : ""
      }`}
    >
      <span className="mt-0.5 w-4 shrink-0 text-right font-mono text-xs text-zinc-400">
        {index + 1}
      </span>
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
          <span
            className={`text-sm ${removed ? "text-zinc-400 line-through" : "text-zinc-200"}`}
          >
            {humanizeOp(step.op)}
          </span>
        </div>
        {step.description && (
          <p
            className={`measure mt-0.5 text-xs leading-relaxed ${
              removed ? "text-zinc-400 line-through" : "text-zinc-400"
            }`}
          >
            {step.description}
          </p>
        )}
        {step.columns.length > 0 && (
          <div className="mt-1.5 flex flex-wrap gap-1">
            {step.columns.map((c) => (
              <ColumnChip key={c}>{c}</ColumnChip>
            ))}
          </div>
        )}
      </div>
      {onToggleRemove &&
        (removable ? (
          <button
            onClick={onToggleRemove}
            title={removed ? "Restore step" : "Remove step"}
            className="focus-ring-panel shrink-0 rounded px-1.5 py-0.5 text-xs text-zinc-400 transition-colors hover:text-red-300"
          >
            {removed ? "↺" : "×"}
          </button>
        ) : (
          <span
            title="required"
            className="shrink-0 rounded px-1.5 py-0.5 text-xs text-zinc-400"
          >
            •
          </span>
        ))}
    </div>
  );
}
