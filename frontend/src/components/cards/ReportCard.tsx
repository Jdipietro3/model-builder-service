"use client";

import { api, Diagnostics, DiagnosticsCalibration, DiagnosticsSegment, Results } from "@/lib/api";

// Sequential hue for magnitude encodings (importance bars, matrix cells) —
// dark-surface step of the reference palette's blue ramp.
const SEQ_HUE = "#3987e5";
const GOOD = "#0ca30c";
const BAD = "#e66767";

// All forecasting metrics (mase/mape/smape) are lower-is-better, like mae/rmse.
// Exported for reuse by ComparisonCard (retrain vs. prior-run metric deltas).
export const LOWER_BETTER = new Set(["mae", "rmse", "mase", "mape", "smape"]);
export const METRIC_LABELS: Record<string, string> = {
  roc_auc: "ROC-AUC",
  pr_auc: "PR-AUC",
  f1: "F1",
  f1_macro: "F1 (macro)",
  accuracy: "Accuracy",
  balanced_accuracy: "Balanced accuracy",
  r2: "R²",
  mae: "MAE",
  rmse: "RMSE",
  mase: "MASE",
  mape: "MAPE",
  smape: "sMAPE",
};

// Chart palette (mirrors the tokens used by ImportanceBars / ConfusionMatrix).
const ACTUAL_HUE = "#d4d4d8"; // zinc-300 — observed values
const PRED_HUE = "#3987e5"; // blue — backtest predictions
const FORECAST_HUE = "#10b981"; // emerald — future forecast

export function fmt(v: number): string {
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

function ImportanceBars({ items }: { items: NonNullable<Results["feature_importances"]> }) {
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

function LegendSwatch({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-[11px] text-zinc-400">
      <span
        className="inline-block h-0.5 w-4 rounded"
        style={dashed ? { borderTop: `2px dashed ${color}`, height: 0 } : { background: color }}
      />
      {label}
    </span>
  );
}

/**
 * Hand-rolled inline SVG forecast chart (no chart library). Draws, along a shared
 * index-scaled time axis: history_tail actuals + holdout actual/predicted +
 * forecast yhat, with shaded prediction-interval bands and a divider at the
 * point where the forecast (future) begins. Any missing/empty block is skipped.
 */
function ForecastChart({ results }: { results: Results }) {
  const hist = results.history_tail;
  const ho = results.holdout_series;
  const fc = results.forecast;

  const histLen = hist?.actual?.length ?? 0;
  const holdoutLen = ho?.actual?.length ?? 0;
  const forecastLen = fc?.yhat?.length ?? 0;
  const N = histLen + holdoutLen + forecastLen;
  if (N < 2) return null; // nothing meaningful to plot

  // Layout (viewBox coordinates; rendered responsively at 100% width).
  const W = 720;
  const H = 260;
  const padL = 48;
  const padR = 12;
  const padT = 12;
  const padB = 24;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // Collect every finite y-value to derive the value scale.
  const ys: number[] = [];
  if (hist) ys.push(...hist.actual);
  if (ho) ys.push(...ho.actual, ...ho.predicted, ...ho.lower, ...ho.upper);
  if (fc) ys.push(...fc.yhat, ...fc.lower, ...fc.upper);
  const finite = ys.filter((v) => Number.isFinite(v));
  if (finite.length === 0) return null;
  let min = Math.min(...finite);
  let max = Math.max(...finite);
  if (min === max) {
    // Degenerate flat series — pad so the line renders mid-plot.
    min -= 1;
    max += 1;
  }
  const range = max - min;

  const x = (i: number) => padL + (N === 1 ? 0 : (i / (N - 1)) * plotW);
  const y = (v: number) => padT + (1 - (v - min) / range) * plotH;

  const linePts = (startIdx: number, vals: number[]) =>
    vals.map((v, k) => `${x(startIdx + k)},${y(v)}`).join(" ");

  const bandPath = (startIdx: number, lower: number[], upper: number[]) => {
    const top = upper.map((v, k) => `${x(startIdx + k)},${y(v)}`);
    const bot = lower.map((v, k) => `${x(startIdx + k)},${y(v)}`).reverse();
    if (top.length === 0) return "";
    return `M ${[...top, ...bot].join(" L ")} Z`;
  };

  const holdoutStart = histLen;
  const forecastStart = histLen + holdoutLen;

  // Contiguous observed line: history actuals followed by holdout actuals.
  const actualVals = [...(hist?.actual ?? []), ...(ho?.actual ?? [])];

  // Bridge the forecast line back to the last observed point for continuity.
  const lastActual =
    ho && ho.actual.length ? ho.actual[ho.actual.length - 1] : hist && hist.actual.length ? hist.actual[hist.actual.length - 1] : undefined;
  const fcLineStart = forecastLen && lastActual !== undefined ? forecastStart - 1 : forecastStart;
  const fcLineVals =
    forecastLen && lastActual !== undefined ? [lastActual, ...(fc?.yhat ?? [])] : fc?.yhat ?? [];

  // Y ticks (4 evenly spaced labels).
  const ticks = [0, 1, 2, 3].map((k) => min + (range * k) / 3);

  // Divider at the start of the future (between last holdout and first forecast).
  const showDivider = forecastLen > 0 && forecastStart > 0;
  const xDivider = showDivider ? (x(forecastStart - 1) + x(forecastStart)) / 2 : 0;

  const firstTs =
    hist?.timestamps?.[0] ?? ho?.timestamps?.[0] ?? fc?.timestamps?.[0] ?? "";
  const lastArr = fc?.timestamps ?? ho?.timestamps ?? hist?.timestamps ?? [];
  const lastTs = lastArr[lastArr.length - 1] ?? "";
  const dateLabel = (s: string) => (s ? s.slice(0, 10) : "");

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h4 className="text-xs font-medium uppercase tracking-wide text-zinc-500">Forecast</h4>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <LegendSwatch color={ACTUAL_HUE} label="Actual" />
          {holdoutLen > 0 && <LegendSwatch color={PRED_HUE} label="Backtest" />}
          {forecastLen > 0 && <LegendSwatch color={FORECAST_HUE} label="Forecast" />}
          <LegendSwatch color="#52525b" label="Interval" />
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="overflow-visible" role="img" aria-label="Forecast chart">
        {/* Y grid + tick labels */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="#27272a" strokeWidth={1} />
            <text
              x={padL - 6}
              y={y(t)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={10}
              fill="#71717a"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {fmt(t)}
            </text>
          </g>
        ))}

        {/* Prediction-interval bands */}
        {ho && ho.lower.length > 0 && (
          <path d={bandPath(holdoutStart, ho.lower, ho.upper)} fill="rgba(57,135,229,0.14)" stroke="none" />
        )}
        {fc && fc.lower.length > 0 && (
          <path d={bandPath(forecastStart, fc.lower, fc.upper)} fill="rgba(16,185,129,0.14)" stroke="none" />
        )}

        {/* Divider where the future begins */}
        {showDivider && (
          <line
            x1={xDivider}
            x2={xDivider}
            y1={padT}
            y2={H - padB}
            stroke="#52525b"
            strokeWidth={1}
            strokeDasharray="3 3"
          />
        )}

        {/* Observed (history + holdout actuals) */}
        {actualVals.length > 0 && (
          <polyline
            points={linePts(0, actualVals)}
            fill="none"
            stroke={ACTUAL_HUE}
            strokeWidth={1.75}
            strokeLinejoin="round"
          />
        )}
        {/* Backtest predictions over the holdout window */}
        {ho && ho.predicted.length > 0 && (
          <polyline
            points={linePts(holdoutStart, ho.predicted)}
            fill="none"
            stroke={PRED_HUE}
            strokeWidth={1.75}
            strokeLinejoin="round"
          />
        )}
        {/* Future forecast */}
        {fcLineVals.length > 0 && (
          <polyline
            points={linePts(fcLineStart, fcLineVals)}
            fill="none"
            stroke={FORECAST_HUE}
            strokeWidth={1.75}
            strokeDasharray="5 3"
            strokeLinejoin="round"
          />
        )}

        {/* X endpoints */}
        <text x={padL} y={H - 6} textAnchor="start" fontSize={10} fill="#71717a">
          {dateLabel(firstTs)}
        </text>
        <text x={W - padR} y={H - 6} textAnchor="end" fontSize={10} fill="#71717a">
          {dateLabel(lastTs)}
        </text>
      </svg>
    </div>
  );
}

/** Compact per-column segment breakdown table, worst-performing segment highlighted. */
function SegmentTable({ segment }: { segment: DiagnosticsSegment }) {
  const label = METRIC_LABELS[segment.metric] ?? segment.metric;
  const lowerBetter = LOWER_BETTER.has(segment.metric);
  return (
    <div>
      <div className="mb-1.5 flex items-baseline justify-between gap-2">
        <span className="font-mono text-xs text-zinc-300">{segment.column}</span>
        <span className="text-[11px] text-zinc-500">
          overall {label} {fmt(segment.overall)}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs" style={{ fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr className="text-zinc-500">
              <th className="pb-1 pr-3 text-left font-normal">Segment</th>
              <th className="pb-1 pr-3 text-right font-normal">n</th>
              {Object.keys(segment.segments[0]?.metrics ?? {}).map((k) => (
                <th key={k} className="pb-1 pr-3 text-right font-normal">
                  {METRIC_LABELS[k] ?? k}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {segment.segments.map((s) => {
              const isWorst = s.value === segment.worst.value && s.n === segment.worst.n;
              return (
                <tr
                  key={s.value}
                  className={isWorst ? "bg-red-950/30" : undefined}
                >
                  <td
                    className={`py-1 pr-3 ${isWorst ? "text-red-300" : "text-zinc-300"}`}
                    title={isWorst ? `Weakest segment (${lowerBetter ? "highest" : "lowest"} ${label})` : undefined}
                  >
                    {isWorst && <span className="mr-1">⚠</span>}
                    {s.value}
                  </td>
                  <td className="py-1 pr-3 text-right text-zinc-500">{s.n.toLocaleString()}</td>
                  {Object.entries(s.metrics).map(([k, v]) => (
                    <td
                      key={k}
                      className={`py-1 pr-3 text-right ${isWorst ? "text-red-300" : "text-zinc-300"}`}
                    >
                      {fmt(v)}
                    </td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/** Lightweight reliability plot (predicted vs. observed positive rate per bin) — inline SVG, no chart lib. */
function CalibrationView({ calibration }: { calibration: DiagnosticsCalibration }) {
  const { brier, bins } = calibration;
  const W = 200;
  const H = 200;
  const pad = 20;
  const plot = W - pad * 2;
  const maxN = Math.max(...bins.map((b) => b.n), 1);
  const px = (v: number) => pad + Math.min(Math.max(v, 0), 1) * plot;
  const py = (v: number) => H - pad - Math.min(Math.max(v, 0), 1) * plot;

  return (
    <div>
      <div className="mb-2 flex items-baseline justify-between">
        <h4 className="text-xs font-medium uppercase tracking-wide text-zinc-500">Calibration</h4>
        <span className="text-xs text-zinc-400">
          Brier score <span className="font-mono text-zinc-300">{fmt(brier)}</span>{" "}
          <span className="text-zinc-600">(lower is better)</span>
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <svg viewBox={`0 0 ${W} ${H}`} width={180} height={180} className="shrink-0" role="img" aria-label="Reliability diagram">
          {/* diagonal = perfect calibration */}
          <line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(1)} stroke="#52525b" strokeDasharray="3 3" strokeWidth={1} />
          <line x1={pad} x2={pad} y1={pad} y2={H - pad} stroke="#27272a" strokeWidth={1} />
          <line x1={pad} x2={W - pad} y1={H - pad} y2={H - pad} stroke="#27272a" strokeWidth={1} />
          <text x={pad} y={H - 4} fontSize={9} fill="#71717a">0</text>
          <text x={W - pad} y={H - 4} textAnchor="end" fontSize={9} fill="#71717a">1</text>
          <polyline
            points={bins.map((b) => `${px(b.p_pred)},${py(b.p_true)}`).join(" ")}
            fill="none"
            stroke={SEQ_HUE}
            strokeWidth={1.5}
          />
          {bins.map((b, i) => (
            <circle
              key={i}
              cx={px(b.p_pred)}
              cy={py(b.p_true)}
              r={2 + 4 * Math.sqrt(b.n / maxN)}
              fill={SEQ_HUE}
              fillOpacity={0.75}
            >
              <title>{`predicted ${fmt(b.p_pred)} · observed ${fmt(b.p_true)} · n=${b.n}`}</title>
            </circle>
          ))}
        </svg>
        <p className="max-w-[16rem] text-[11px] leading-relaxed text-zinc-500">
          Predicted probability (x) vs. actual observed rate (y) per bin, dot size ∝ bin size. Points
          on the dashed diagonal are well-calibrated.
        </p>
      </div>
    </div>
  );
}

function DiagnosticsSection({ diagnostics }: { diagnostics: Diagnostics }) {
  const { segments, calibration, single_feature } = diagnostics;
  const leaky = single_feature.filter((f) => f.ratio >= 0.95);
  const topFeature = single_feature[0];

  if (segments.length === 0 && !calibration && single_feature.length === 0) return null;

  return (
    <div className="space-y-4 rounded-lg border border-zinc-800 bg-zinc-900/40 px-3 py-3">
      <h4 className="text-xs font-medium uppercase tracking-wide text-zinc-500">
        Diagnostics — where this model is trustworthy
      </h4>

      {leaky.length > 0 && (
        <div className="rounded-lg border border-red-900/70 bg-red-950/30 px-3 py-2.5">
          {leaky.map((f) => (
            <p key={f.feature} className="text-xs leading-relaxed text-red-200/90">
              ⚠ <span className="font-mono">{f.feature}</span> alone reaches{" "}
              <span className="font-semibold">{(f.ratio * 100).toFixed(0)}%</span> of full model
              performance ({fmt(f.solo_score)} vs {fmt(f.full_score)}) — likely leakage.
            </p>
          ))}
        </div>
      )}
      {leaky.length === 0 && topFeature && (
        <p className="text-[11px] text-zinc-500">
          Top single feature <span className="font-mono text-zinc-400">{topFeature.feature}</span>{" "}
          alone reaches {(topFeature.ratio * 100).toFixed(0)}% of full model performance —
          within normal range.
        </p>
      )}

      {segments.length > 0 && (
        <div className="space-y-3">
          {segments.map((s) => (
            <SegmentTable key={s.column} segment={s} />
          ))}
        </div>
      )}

      {calibration && <CalibrationView calibration={calibration} />}
    </div>
  );
}

export default function ReportCard({ runId, results }: { runId: string; results: Results }) {
  const { holdout } = results;
  const primary = results.primary_metric;
  const secondary = Object.keys(holdout.metrics).filter((m) => m !== primary);
  const isForecasting =
    results.task_family === "forecasting" || results.task_type === "forecasting";

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
            {results.n_test.toLocaleString()} {isForecasting ? "holdout points" : "test rows"}
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
          Baseline = {holdout.baseline_description}.{" "}
          {isForecasting ? "Rolling-origin backtest" : "Cross-validation"} {results.cv.metric}:{" "}
          {fmt(results.cv.mean)} ± {fmt(results.cv.std)} over {results.cv.n_splits}{" "}
          {isForecasting ? "backtest folds" : "folds"}.
        </p>

        {isForecasting && <ForecastChart results={results} />}

        {!isForecasting && holdout.confusion_matrix && (
          <ConfusionMatrix
            labels={holdout.confusion_matrix.labels}
            matrix={holdout.confusion_matrix.matrix}
          />
        )}

        {!isForecasting && holdout.residuals && (
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

        {results.diagnostics && <DiagnosticsSection diagnostics={results.diagnostics} />}

        {!isForecasting && results.feature_importances && (
          <ImportanceBars items={results.feature_importances} />
        )}

        {!isForecasting && results.features_dropped && results.features_dropped.length > 0 && (
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
