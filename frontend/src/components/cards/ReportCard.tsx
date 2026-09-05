"use client";

import { ReactNode } from "react";
import { api, Diagnostics, DiagnosticsCalibration, DiagnosticsSegment, Results } from "@/lib/api";

// Chart palette — single source of truth is the token set in globals.css
// (var(--chart-*)). Constants below just give the SVG/JS call sites a short
// name; nothing here re-declares a color the tokens don't already own.
const SEQ_HUE = "var(--chart-seq)";
const GOOD = "var(--chart-good)";
const BAD = "var(--chart-bad)";
const ACTUAL_HUE = "var(--chart-actual)"; // observed values
const PRED_HUE = "var(--chart-seq)"; // backtest predictions
const FORECAST_HUE = "var(--chart-forecast)"; // future forecast

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

// Plain-language definitions for the metric glossary disclosure — the
// primary-persona fix. Keep each one to a single short sentence.
const METRIC_DESCRIPTIONS: Record<string, string> = {
  roc_auc: "Probability the model ranks a random positive above a random negative. 1.0 is perfect, 0.5 is a coin flip.",
  pr_auc: "Like ROC-AUC but focused on the positive class — more informative when positives are rare.",
  f1: "Balances false positives and false negatives into one number.",
  f1_macro: "F1 averaged equally across classes, so rare classes count as much as common ones.",
  accuracy: "Share of predictions that were exactly correct.",
  balanced_accuracy: "Accuracy averaged per class, so a large majority class can't hide poor performance elsewhere.",
  r2: "Share of the target's variance the model explains. 1.0 is perfect, 0 is no better than guessing the mean.",
  mae: "Mean absolute error — the average size of the miss, in the target's own units.",
  rmse: "Root mean squared error — like MAE but penalizes large misses more heavily.",
  mase: "Error relative to a naive seasonal forecast. Below 1 means it beats that baseline.",
  mape: "Average miss size as a percent of the true value.",
  smape: "A percentage error that treats over- and under-forecasts evenly.",
};

// --- WCAG contrast helpers (used to pick text ink for the confusion matrix,
// where the background is computed at render time and can't be pre-audited
// like a static token). Standard sRGB relative-luminance formula.
type RGB = [number, number, number];

function srgbToLinear(c: number): number {
  const cs = c / 255;
  return cs <= 0.03928 ? cs / 12.92 : Math.pow((cs + 0.055) / 1.055, 2.4);
}

function relativeLuminance([r, g, b]: RGB): number {
  return 0.2126 * srgbToLinear(r) + 0.7152 * srgbToLinear(g) + 0.0722 * srgbToLinear(b);
}

function contrastRatio(a: RGB, b: RGB): number {
  const la = relativeLuminance(a);
  const lb = relativeLuminance(b);
  const lighter = Math.max(la, lb);
  const darker = Math.min(la, lb);
  return (lighter + 0.05) / (darker + 0.05);
}

export function fmt(v: number): string {
  if (Math.abs(v) >= 1000) return v.toLocaleString(undefined, { maximumFractionDigits: 0 });
  return v.toLocaleString(undefined, { maximumFractionDigits: 3 });
}

function ChevronIcon() {
  return (
    <svg
      viewBox="0 0 16 16"
      width={12}
      height={12}
      className="shrink-0 text-zinc-400 transition-transform duration-150 group-open:rotate-90"
      aria-hidden="true"
    >
      <path d="M6 3l5 5-5 5" fill="none" stroke="currentColor" strokeWidth={1.75} strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/**
 * Native <details>/<summary> disclosure styled to match the card idiom.
 * Keyboard-accessible with no state required. `summary` must state what's
 * inside in plain language — it's the only thing visible when collapsed.
 */
function Disclosure({
  summary,
  detail,
  defaultOpen,
  children,
}: {
  summary: string;
  detail?: string;
  defaultOpen?: boolean;
  children: ReactNode;
}) {
  return (
    <details className="group border-t border-zinc-800 pt-4" open={defaultOpen}>
      <summary
        className="flex list-none cursor-pointer items-center justify-between gap-3 rounded focus-ring-panel [&::-webkit-details-marker]:hidden"
      >
        <span className="flex flex-col gap-0.5">
          <span className="text-xs font-medium uppercase tracking-wide text-zinc-400">{summary}</span>
          {detail && <span className="text-xs normal-case text-zinc-400">{detail}</span>}
        </span>
        <ChevronIcon />
      </summary>
      <div className="pt-3">{children}</div>
    </details>
  );
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
      <div className="mt-1 text-xs text-zinc-400">
        baseline {fmt(baseline)}{" "}
        <span style={{ color: improved ? GOOD : BAD }}>{improved ? "▲ beats it" : "▼ doesn't beat it"}</span>
      </div>
    );
  }
  return (
    <div
      // Background shift, not a nested border: these tiles sit inside an
      // already-bordered card, and a box inside a box is a nested card. The
      // primary tile earns its rank from a lighter surface, not an outline.
      className={`rounded-lg px-3 py-2.5 ${primary ? "bg-zinc-800/80" : "bg-zinc-950/40"}`}
    >
      <div className="text-xs text-zinc-400">
        {METRIC_LABELS[name] ?? name}
        {primary && <span className="ml-1.5 text-xs text-accent">optimized</span>}
      </div>
      <div className={`font-mono font-semibold text-accent-bright ${primary ? "text-2xl" : "text-lg"}`}>
        {fmt(value)}
      </div>
      {deltaEl}
    </div>
  );
}

/** Compact glossary for the metric tiles above — discoverable without hover, unlike a `title` attribute. */
function MetricGlossary({ metrics }: { metrics: string[] }) {
  const known = metrics.filter((m) => METRIC_DESCRIPTIONS[m]);
  if (known.length === 0) return null;
  return (
    <Disclosure summary="What these metrics mean" detail="Plain-language definitions for the tiles above" defaultOpen>
      {/* `measure` sits on the element that carries the font size, not the <dl>:
          `ch` resolves against the element's own font-size, so capping at the
          14px parent would let 12px text run ~40% wider than intended. */}
      <dl className="space-y-2">
        {known.map((m) => (
          <div key={m} className="measure text-xs">
            <dt className="inline font-medium text-zinc-300">{METRIC_LABELS[m] ?? m}</dt>
            <dd className="inline text-zinc-400"> — {METRIC_DESCRIPTIONS[m]}</dd>
          </div>
        ))}
      </dl>
    </Disclosure>
  );
}

function ImportanceBars({ items }: { items: NonNullable<Results["feature_importances"]> }) {
  const top = items.filter((i) => i.importance > 0).slice(0, 8);
  if (top.length === 0) return null;
  const max = Math.max(...top.map((i) => i.importance));
  return (
    <div>
      <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
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
                className="text-xs text-zinc-400"
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

// Numeric mirror of var(--chart-seq) (#ab6e1f, the amber ramp's --seq-5),
// needed because the ink-color choice below requires real RGB math (composite
// the cell over the panel, compute luminance) that CSS custom properties
// cannot do for us at render time. Keep this in sync with --chart-seq by hand;
// there is no mechanism that will catch it drifting.
//
// Darkened slightly before blending, for the same reason the old sky version
// was: at full brightness some alpha step always lands in a "too bright for
// dark ink, too mid-tone for light ink" zone that tops out at 4.26:1 against
// BOTH inks and fails AA no matter which one is chosen. Darkening pulls the
// ramp's luminance down until light ink clears AA across the whole range.
//
// The factor was re-derived when the palette moved from sky to amber rather
// than carried over — the old 0.72 was tuned to a different hue and means
// nothing here. Verified by walking the full alpha range (0.08 → 0.93) in
// 0.2%-of-range steps: at 0.9 the worst case is 5.02:1, slightly better than
// the 4.99:1 the sky version achieved, and 0.9 is the lightest factor that
// clears the plateau — anything nearer 1.0 falls back onto 4.26 and fails.
const SEQ_RGB: RGB = [171, 110, 31];
const SEQ_FILL_RGB: RGB = SEQ_RGB.map((c) => c * 0.9) as RGB;
const PANEL_RGB: RGB = [24, 24, 27]; // Ink Panel (#18181b) — the surface these cells sit on
const LIGHT_INK: RGB = [244, 244, 245]; // #f4f4f5
const DARK_INK: RGB = [9, 9, 11]; // #09090b

function ConfusionMatrix({ labels, matrix }: { labels: string[]; matrix: number[][] }) {
  const maxCell = Math.max(...matrix.flat(), 1);
  return (
    <div>
      <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
        Confusion matrix <span className="normal-case">(rows = actual, columns = predicted)</span>
      </h4>
      <div className="overflow-x-auto">
        <table className="text-xs" style={{ fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr>
              <th />
              {labels.map((l) => (
                <th key={l} className="px-1 pb-1 text-center font-mono font-normal text-zinc-400">
                  {l}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {matrix.map((row, i) => (
              <tr key={i}>
                <td className="pr-2 text-right font-mono text-zinc-400">{labels[i]}</td>
                {row.map((cell, j) => {
                  const alpha = 0.08 + 0.85 * (cell / maxCell);
                  const composite: RGB = [0, 1, 2].map(
                    (k) => SEQ_FILL_RGB[k] * alpha + PANEL_RGB[k] * (1 - alpha)
                  ) as RGB;
                  const ink =
                    contrastRatio(composite, LIGHT_INK) >= contrastRatio(composite, DARK_INK)
                      ? "#f4f4f5"
                      : "#09090b";
                  return (
                    <td key={j} className="p-0.5">
                      <div
                        className="flex h-10 w-16 items-center justify-center rounded"
                        title={`actual ${labels[i]}, predicted ${labels[j]}: ${cell.toLocaleString()}`}
                        style={{
                          background: `rgba(${SEQ_FILL_RGB[0].toFixed(1)}, ${SEQ_FILL_RGB[1].toFixed(1)}, ${SEQ_FILL_RGB[2].toFixed(1)}, ${alpha.toFixed(2)})`,
                          color: ink,
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
    <span className="inline-flex items-center gap-1.5 text-xs text-zinc-400">
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
        <h4 className="text-xs font-medium uppercase tracking-wide text-zinc-400">Forecast</h4>
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <LegendSwatch color={ACTUAL_HUE} label="Actual" />
          {holdoutLen > 0 && <LegendSwatch color={PRED_HUE} label="Backtest" />}
          {forecastLen > 0 && <LegendSwatch color={FORECAST_HUE} label="Forecast" />}
          <LegendSwatch color="var(--chart-neutral)" label="Interval" />
        </div>
      </div>
      <svg viewBox={`0 0 ${W} ${H}`} width="100%" className="overflow-visible" role="img" aria-label="Forecast chart">
        {/* Y grid + tick labels */}
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={padL} x2={W - padR} y1={y(t)} y2={y(t)} stroke="var(--chart-grid)" strokeWidth={1} />
            <text
              x={padL - 6}
              y={y(t)}
              textAnchor="end"
              dominantBaseline="middle"
              fontSize={12}
              fill="var(--chart-axis)"
              style={{ fontVariantNumeric: "tabular-nums" }}
            >
              {fmt(t)}
            </text>
          </g>
        ))}

        {/* Prediction-interval bands */}
        {ho && ho.lower.length > 0 && (
          <path
            d={bandPath(holdoutStart, ho.lower, ho.upper)}
            fill="color-mix(in srgb, var(--chart-seq) 14%, transparent)"
            stroke="none"
          />
        )}
        {fc && fc.lower.length > 0 && (
          <path
            d={bandPath(forecastStart, fc.lower, fc.upper)}
            fill="color-mix(in srgb, var(--chart-forecast) 14%, transparent)"
            stroke="none"
          />
        )}

        {/* Divider where the future begins */}
        {showDivider && (
          <line
            x1={xDivider}
            x2={xDivider}
            y1={padT}
            y2={H - padB}
            stroke="var(--chart-neutral)"
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
        <text x={padL} y={H - 6} textAnchor="start" fontSize={12} fill="var(--chart-axis)">
          {dateLabel(firstTs)}
        </text>
        <text x={W - padR} y={H - 6} textAnchor="end" fontSize={12} fill="var(--chart-axis)">
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
        <span className="text-xs text-zinc-400">
          overall {label} {fmt(segment.overall)}
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-xs" style={{ fontVariantNumeric: "tabular-nums" }}>
          <thead>
            <tr className="text-zinc-400">
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
                  className={isWorst ? "bg-alarm-wash" : undefined}
                >
                  <td
                    className={`py-1 pr-3 ${isWorst ? "text-alarm" : "text-zinc-300"}`}
                    title={isWorst ? `Weakest segment (${lowerBetter ? "highest" : "lowest"} ${label})` : undefined}
                  >
                    {isWorst && <span className="mr-1">⚠</span>}
                    {s.value}
                  </td>
                  <td className="py-1 pr-3 text-right text-zinc-400">{s.n.toLocaleString()}</td>
                  {Object.entries(s.metrics).map(([k, v]) => (
                    <td
                      key={k}
                      className={`py-1 pr-3 text-right ${isWorst ? "text-alarm" : "text-zinc-300"}`}
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
        <h5 className="text-xs font-medium uppercase tracking-wide text-zinc-400">Calibration</h5>
        <span className="text-xs text-zinc-400">
          Brier score <span className="font-mono text-accent-bright">{fmt(brier)}</span>{" "}
          <span className="text-zinc-400">(lower is better)</span>
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-4">
        <svg viewBox={`0 0 ${W} ${H}`} width={180} height={180} className="shrink-0" role="img" aria-label="Reliability diagram">
          {/* diagonal = perfect calibration */}
          <line x1={px(0)} y1={py(0)} x2={px(1)} y2={py(1)} stroke="var(--chart-neutral)" strokeDasharray="3 3" strokeWidth={1} />
          <line x1={pad} x2={pad} y1={pad} y2={H - pad} stroke="var(--chart-grid)" strokeWidth={1} />
          <line x1={pad} x2={W - pad} y1={H - pad} y2={H - pad} stroke="var(--chart-grid)" strokeWidth={1} />
          <text x={pad} y={H - 4} fontSize={12} fill="var(--chart-axis)">0</text>
          <text x={W - pad} y={H - 4} textAnchor="end" fontSize={12} fill="var(--chart-axis)">1</text>
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
        <p className="max-w-[16rem] text-xs leading-relaxed text-zinc-400">
          Predicted probability (x) vs. actual observed rate (y) per bin, dot size ∝ bin size. Points
          on the dashed diagonal are well-calibrated.
        </p>
      </div>
    </div>
  );
}

/** Leakage / single-feature trust check — the content of the default-open diagnostics disclosure. */
function LeakageCheck({ diagnostics }: { diagnostics: Diagnostics }) {
  const { single_feature } = diagnostics;
  const leaky = single_feature.filter((f) => f.ratio >= 0.95);
  const topFeature = single_feature[0];
  if (single_feature.length === 0) return null;

  if (leaky.length > 0) {
    return (
      <div className="rounded-lg border border-alarm/40 bg-alarm-wash px-3 py-2.5">
        {leaky.map((f) => (
          <p key={f.feature} className="measure text-xs leading-relaxed text-alarm">
            ⚠ <span className="font-mono">{f.feature}</span> alone reaches{" "}
            <span className="font-semibold">{(f.ratio * 100).toFixed(0)}%</span> of full model
            performance ({fmt(f.solo_score)} vs {fmt(f.full_score)}) — likely leakage.
          </p>
        ))}
      </div>
    );
  }
  if (topFeature) {
    return (
      <p className="measure text-xs text-zinc-400">
        Top single feature <span className="font-mono text-zinc-300">{topFeature.feature}</span>{" "}
        alone reaches {(topFeature.ratio * 100).toFixed(0)}% of full model performance —
        within normal range.
      </p>
    );
  }
  return null;
}

export default function ReportCard({ runId, results }: { runId: string; results: Results }) {
  const { holdout } = results;
  const primary = results.primary_metric;
  const secondary = Object.keys(holdout.metrics).filter((m) => m !== primary);
  const isForecasting =
    results.task_family === "forecasting" || results.task_type === "forecasting";

  const diagnostics = results.diagnostics;
  const hasLeakageCheck = !!diagnostics && diagnostics.single_feature.length > 0;
  const leakyCount = diagnostics ? diagnostics.single_feature.filter((f) => f.ratio >= 0.95).length : 0;
  const hasSegments = !!diagnostics && diagnostics.segments.length > 0;
  const hasCalibration = !!diagnostics && !!diagnostics.calibration;

  return (
    <div className="overflow-hidden rounded-xl border border-zinc-700 bg-zinc-900/80">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 px-4 py-3">
        <div className="flex items-center gap-2">
          <span className="rounded bg-accent-wash px-2 py-0.5 text-xs font-medium text-accent">
            RESULTS
          </span>
          <h3 className="text-sm text-zinc-300">{results.methodology.display_name}</h3>
          <span className="text-xs text-zinc-400">
            trained in {results.training_seconds}s · {results.n_train.toLocaleString()} train /{" "}
            {results.n_test.toLocaleString()} {isForecasting ? "holdout points" : "test rows"}
          </span>
        </div>
        <a
          href={api.artifactUrl(runId)}
          className="focus-ring-panel rounded px-3 py-1.5 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-accent"
        >
          ↓ Download model bundle
        </a>
      </div>

      <div className="space-y-5 px-4 py-4">
        <div className="space-y-2">
          <MetricTile
            name={primary}
            value={holdout.metrics[primary]}
            baseline={holdout.baseline_metrics[primary]}
            primary
          />
          {secondary.length > 0 && (
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-4">
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
          )}
        </div>
        <p className="measure text-xs text-zinc-400">
          Baseline = {holdout.baseline_description}.{" "}
          {isForecasting ? "Rolling-origin backtest" : "Cross-validation"} {results.cv.metric}:{" "}
          {fmt(results.cv.mean)} ± {fmt(results.cv.std)} over {results.cv.n_splits}{" "}
          {isForecasting ? "backtest folds" : "folds"}.
        </p>

        <MetricGlossary metrics={[primary, ...secondary]} />

        {isForecasting && <ForecastChart results={results} />}

        {!isForecasting && holdout.confusion_matrix && (
          <ConfusionMatrix
            labels={holdout.confusion_matrix.labels}
            matrix={holdout.confusion_matrix.matrix}
          />
        )}

        {!isForecasting && holdout.residuals && (
          <div>
            <h4 className="mb-2 text-xs font-medium uppercase tracking-wide text-zinc-400">
              Prediction errors (residuals)
            </h4>
            <p className="measure text-sm text-zinc-300">
              80% of predictions land within{" "}
              <span className="font-mono text-accent-bright">{fmt(holdout.residuals.p10)}</span> to{" "}
              <span className="font-mono text-accent-bright">+{fmt(holdout.residuals.p90)}</span> of the true value
              (target mean {fmt(holdout.residuals.target_mean)}).
            </p>
          </div>
        )}

        {hasLeakageCheck && diagnostics && (
          <Disclosure
            summary="Diagnostics — trust check"
            detail={
              leakyCount > 0
                ? `${leakyCount} feature${leakyCount > 1 ? "s" : ""} may be leaking the answer`
                : "No single feature dominates — looks trustworthy"
            }
            defaultOpen
          >
            <LeakageCheck diagnostics={diagnostics} />
          </Disclosure>
        )}

        {hasSegments && diagnostics && (
          <Disclosure
            summary="Per-segment breakdown"
            detail={`Performance across ${diagnostics.segments.length} column${diagnostics.segments.length > 1 ? "s" : ""} — weakest subgroup highlighted`}
          >
            <div className="space-y-3">
              {diagnostics.segments.map((s) => (
                <SegmentTable key={s.column} segment={s} />
              ))}
            </div>
          </Disclosure>
        )}

        {hasCalibration && diagnostics?.calibration && (
          <Disclosure
            summary="Calibration"
            detail={`How well predicted probabilities match reality — Brier ${fmt(diagnostics.calibration.brier)}`}
          >
            <CalibrationView calibration={diagnostics.calibration} />
          </Disclosure>
        )}

        {!isForecasting && results.feature_importances && results.feature_importances.length > 0 && (
          <Disclosure
            summary="What drives predictions"
            detail={`Top ${Math.min(8, results.feature_importances.filter((i) => i.importance > 0).length)} features by importance`}
          >
            <ImportanceBars items={results.feature_importances} />
          </Disclosure>
        )}

        {!isForecasting && results.features_dropped && results.features_dropped.length > 0 && (
          <p className="text-xs text-zinc-400">
            Not used as features:{" "}
            {results.features_dropped.map((f) => `${f.name} (${f.reason})`).join(", ")}
          </p>
        )}

        {results.caveats.length > 0 && (
          <div className="space-y-1.5">
            <div className="text-xs font-medium text-zinc-300">Caveats to check</div>
            <ul className="space-y-1.5">
              {results.caveats.map((c, i) => (
                <li key={i} className="flex items-start gap-2 text-xs leading-relaxed text-zinc-300">
                  <span className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-alarm" />
                  <span className="measure">{c}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
