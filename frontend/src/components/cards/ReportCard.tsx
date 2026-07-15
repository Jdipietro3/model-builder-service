"use client";

import { api, Results } from "@/lib/api";

// Sequential hue for magnitude encodings (importance bars, matrix cells) —
// dark-surface step of the reference palette's blue ramp.
const SEQ_HUE = "#3987e5";
const GOOD = "#0ca30c";
const BAD = "#e66767";

const LOWER_BETTER = new Set(["mae", "rmse"]);
const METRIC_LABELS: Record<string, string> = {
  roc_auc: "ROC-AUC",
  pr_auc: "PR-AUC",
  f1: "F1",
  f1_macro: "F1 (macro)",
  accuracy: "Accuracy",
  balanced_accuracy: "Balanced accuracy",
  r2: "R²",
  mae: "MAE",
  rmse: "RMSE",
};

function fmt(v: number): string {
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return v.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function MetricTile({
  name,
  value,
  baseline,
  primary,
}: {
  name: string;
  value: number;
  baseline: number | undefined;
  primary: boolean;
}) {
  const lowerBetter = LOWER_BETTER.has(name);
  let deltaEl = null;
  if (baseline !== undefined) {
    const improved = lowerBetter ? value < baseline : value > baseline;
    deltaEl = (
      <div className="mt-1 text-xs text-zinc-500">
        baseline {fmt(baseline)}{" "}
        <span style={{ color: improved ? GOOD : BAD }}>{improved ? "▲ beats it" : "▼ doesn't beat it"}</span>
      </div>
    );
  }
  return (
    <div
      className={`rounded-lg border px-3 py-2.5 ${
        primary ? "border-zinc-600 bg-zinc-800/60" : "border-zinc-800 bg-zinc-900/40"
      }`}
    >
      <div className="text-xs text-zinc-500">
        {METRIC_LABELS[name] ?? name}
        {primary && <span className="ml-1.5 text-[10px] text-emerald-500">optimized</span>}
      </div>
      <div className={`font-semibold text-zinc-100 ${primary ? "text-2xl" : "text-lg"}`}>
        {fmt(value)}
      </div>
      {deltaEl}
    </div>
  );
}

function ImportanceBars({ items }: { items: Results["feature_importances"] }) {
  const top = items.filter((i) => i.importance > 0).slice(0, 8);
  if (top.length === 0) return null;
  const max = Math.max(...top.map((i) => i.importance));
  return (
    <div>
      <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
        What drives predictions
      </h4>
      <div className="space-y-1.5">
        {top.map((item) => (
          <div
            key={item.feature}
            className="flex items-center gap-2"
            title={`Permutation importance ${item.importance} ± ${item.std}`}
          >
            <span className="w-36 shrink-0 truncate text-right font-mono text-xs text-zinc-300">
              {item.feature}
            </span>
            <div className="flex flex-1 items-center gap-2">
              <div
                className="h-3.5 rounded-r"
                style={{
                  width: `${(item.importance / max) * 100}%`,
                  minWidth: 2,
                  background: SEQ_HUE,
                }}
              />
              <span
                className="text-xs text-zinc-500"
                style={{ fontVariantNumeric: "tabular-nums" }}
              >
                {item.importance.toFixed(3)}
              </span>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ConfusionMatrix({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const maxCell = Math.max(...matrix.flat(), 1);
  return (
    <div>
      <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
        Confusion matrix <span className="normal-case">(rows = actual, columns = predicted)</span>
      </h4>
      <div className="overflow-x-auto">
        <table className="text-xs" style={{ fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr>
              <th />
              {labels.map((l) => (
                <th key={l} className="px-1 pb-1 text-center font-mono font-normal text-zinc-500">
                  {l}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={i}>
                <td className="pr-2 text-right font-mono text-zinc-500">{labels[i]}</td>
                {row.map((cell, j) => {
                  const alpha = 0.08 + 0.85 * (cell / maxCell);
                  return (
                    <td key={j} className="p-0.5">
                      <div
                        className="flex h-10 w-16 items-center justify-center rounded"
                        title={`actual ${labels[i]}, predicted ${labels[j]}: ${cell.toLocaleString()}`}
                        style={{
                          background: `rgba(57, 135, 229, ${alpha.toFixed(2)})`,
                          color: alpha > 0.55 ? "#fff" : "#d4d4d8",
                        }}
                      >
                        {cell.toLocaleString()}
                      </div>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

export default function ReportCard({ runId, results }: { runId: string; results: Results }) {
  const { holdout } = results;
  const primary = results.primary_metric;
  const secondary = Object.keys(holdout.metrics).filter((m) => m !== primary);

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900/80">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-emerald-950 px-2 py-0.5 text-xs font-medium text-emerald-300">
            RESULTS
          </span>
          <span className="text-sm text-zinc-300">{results.methodology.display_name}</span>
          <span className="text-xs text-zinc-500">
            trained in {results.training_seconds}s · {results.n_train.toLocaleString()} train /{" "}
            {results.n_test.toLocaleString()} test rows
          </span>
        </div>
        <a
          href={api.artifactUrl(runId)}
          className="rounded-lg border border-zinc-700 px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:border-emerald-600 hover:text-emerald-400"
        >
          ↓ Download model bundle
        </a>
      </div>

      <div className="space-y-5 px-4 py-4">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <MetricTile
            name={primary}
            value={holdout.metrics[primary]}
            baseline={holdout.baseline_metrics[primary]}
            primary
          />
          {secondary.map((m) => (
            <MetricTile
              key={m}
              name={m}
              value={holdout.metrics[m]}
              baseline={holdout.baseline_metrics[m]}
              primary={false}
            />
          ))}
        </div>
        <p className="text-xs text-zinc-500">
          Baseline = {holdout.baseline_description}. Cross-validation {results.cv.metric}:{" "}
          {fmt(results.cv.mean)} ± {fmt(results.cv.std)} over {results.cv.n_splits} folds.
        </p>

        {holdout.confusion_matrix && (
          <ConfusionMatrix
            labels={holdout.confusion_matrix.labels}
            matrix={holdout.confusion_matrix.matrix}
          />
        )}

        {holdout.residuals && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-500">
              Prediction errors (residuals)
            </h4>
            <p className="text-sm text-zinc-300">
              80% of predictions land within{" "}
              <span className="font-mono">{fmt(holdout.residuals.p10)}</span> to{" "}
              <span className="font-mono">+{fmt(holdout.residuals.p90)}</span> of the true value
              (target mean {fmt(holdout.residuals.target_mean)}).
            </p>
          </div>
        )}

        <ImportanceBars items={results.feature_importances} />

        {results.features_dropped.length > 0 && (
          <p className="text-xs text-zinc-500">
            Not used as features:{" "}
            {results.features_dropped.map((f) => `${f.name} (${f.reason})`).join(", ")}
          </p>
        )}

        {results.caveats.length > 0 && (
          <div className="rounded-lg border border-amber-900/60 bg-amber-950/30 px-3 py-2.5">
            <div className="mb-1 text-xs font-medium text-amber-300">Caveats to check</div>
            <ul className="space-y-1">
              {results.caveats.map((c, i) => (
                <li key={i} className="text-xs leading-relaxed text-amber-200/80">
                  • {c}
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
