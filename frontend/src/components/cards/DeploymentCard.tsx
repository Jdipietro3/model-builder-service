"use client";

import { useEffect, useState } from "react";
import { api, Deployment, Dist, PredictResponse, Run, ServingStats } from "@/lib/api";
import { LOWER_BETTER, METRIC_LABELS, fmt } from "./ReportCard";
import { ConfirmDialog } from "@/components/ConfirmDialog";
import Disclosure from "@/components/Disclosure";

// Sourced from the shared chart tokens in globals.css — one source of truth,
// same hues ReportCard/PredictionCard/ComparisonCard draw from.
const SERVED_HUE = "var(--chart-seq)"; // served (live) distribution
const TRAINING_HUE = "var(--chart-neutral)"; // training-time distribution
const GOOD = "var(--chart-good)";
const BAD = "var(--chart-bad)";

function extractErrorDetail(e: unknown): string {
  const msg = String(e instanceof Error ? e.message : e);
  const jsonStart = msg.indexOf("{");
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(msg.slice(jsonStart));
      if (parsed.detail) return String(parsed.detail);
    } catch {
      // fall through to raw message
    }
  }
  return msg;
}


/** Paired served-vs-training distribution bars — inline SVG, mirrors ReportCard's
 * hand-rolled bar approach. Handles both class_counts (per-label proportion bars)
 * and stats (mean/min/max) shapes; a null `served` renders the empty state. */
function DistComparison({ served, training }: { served: Dist | null; training: Dist }) {
  if (training.kind === "stats") {
    const s = served && served.kind === "stats" ? served : null;
    return (
      <div className="grid grid-cols-3 gap-2">
        {(["mean", "min", "max"] as const).map((k) => (
          <div key={k} className="rounded-lg bg-zinc-950/40 px-3 py-2.5">
            <div className="text-label text-zinc-400">{k}</div>
            <div className="font-mono text-title font-semibold text-accent-bright">
              {s ? fmt(s[k]) : <span className="text-zinc-400">—</span>}
            </div>
            <div className="mt-1 text-label text-zinc-400">training {fmt(training[k])}</div>
          </div>
        ))}
      </div>
    );
  }

  // class_counts
  const trainingProps = training.proportions;
  const servedProps = served && served.kind === "class_counts" ? served.proportions : null;
  const labels = Array.from(
    new Set([...Object.keys(trainingProps), ...Object.keys(servedProps ?? {})]),
  );

  return (
    <div className="space-y-2.5">
      {labels.map((label) => {
        const trainPct = trainingProps[label] ?? 0;
        const servedPct = servedProps ? (servedProps[label] ?? 0) : null;
        return (
          <div key={label}>
            <div className="mb-1 flex items-center justify-between">
              <span className="font-mono text-xs text-zinc-300">{label}</span>
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <span className="w-14 shrink-0 text-right text-label text-zinc-400">served</span>
                <div className="flex flex-1 items-center gap-2">
                  <div
                    className="h-3 rounded-r"
                    style={{
                      width: servedPct !== null ? `${servedPct * 100}%` : "0%",
                      minWidth: servedPct !== null ? 2 : 0,
                      background: SERVED_HUE,
                    }}
                  />
                  <span className="text-label text-zinc-400">
                    {servedPct !== null ? `${(servedPct * 100).toFixed(1)}%` : "no data yet"}
                  </span>
                </div>
              </div>
              <div className="flex items-center gap-2">
                <span className="w-14 shrink-0 text-right text-label text-zinc-400">training</span>
                <div className="flex flex-1 items-center gap-2">
                  <div
                    className="h-3 rounded-r"
                    style={{
                      width: `${trainPct * 100}%`,
                      minWidth: 2,
                      background: TRAINING_HUE,
                    }}
                  />
                  <span className="text-label text-zinc-400">{(trainPct * 100).toFixed(1)}%</span>
                </div>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function StatsPanel({ deploymentId }: { deploymentId: string }) {
  const [stats, setStats] = useState<ServingStats | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function load() {
    try {
      const s = await api.getDeploymentStats(deploymentId);
      setStats(s);
      setError(null);
    } catch (e) {
      setError(extractErrorDetail(e));
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [deploymentId]);

  if (error) {
    return <p className="text-label text-alarm">Could not load serving stats: {error}</p>;
  }
  if (!stats) {
    return <p className="text-label text-zinc-400">Loading serving stats…</p>;
  }

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-3 gap-2">
        <div className="rounded-lg bg-zinc-950/40 px-3 py-2.5">
          <div className="text-label text-zinc-400">Requests</div>
          <div className="font-mono text-title font-semibold text-accent-bright">{stats.n_requests.toLocaleString()}</div>
        </div>
        <div className="rounded-lg bg-zinc-950/40 px-3 py-2.5">
          <div className="text-label text-zinc-400">Rows scored</div>
          <div className="font-mono text-title font-semibold text-accent-bright">{stats.n_rows.toLocaleString()}</div>
        </div>
        <div className="rounded-lg bg-zinc-950/40 px-3 py-2.5">
          <div className="text-label text-zinc-400">Avg latency</div>
          <div className="font-mono text-title font-semibold text-accent-bright">{fmt(stats.avg_latency_ms)} ms</div>
        </div>
      </div>

      {stats.n_requests === 0 ? (
        <p className="text-label text-zinc-400">
          No prediction requests yet — run the live tester below to populate serving stats.
        </p>
      ) : (
        <Disclosure
          tone="label"
          summary="Served vs. training distribution"
          meta="drift indicator"
        >
          <p className="measure mb-2 text-label text-zinc-400">
            Population comparison, not a statistical test — a quick eyeball check for whether
            live traffic looks like the data this model trained on.
          </p>
          <DistComparison served={stats.served_distribution} training={stats.training_distribution} />
        </Disclosure>
      )}
      {stats.drift_note && <p className="measure text-label text-zinc-400">{stats.drift_note}</p>}
    </div>
  );
}

/** Lets the user point this deployment at a DIFFERENT completed run than the
 * one they're currently viewing — a distinct, secondary action from the
 * workspace's one-click "promote this run" button. Collapsed by default so
 * it never competes with the card's primary content. */
function PromoteSection({
  currentRun,
  candidates,
  onPromote,
}: {
  currentRun: Run | null;
  candidates: Run[];
  onPromote: (runId: string) => Promise<void>;
}) {
  const [selectedRunId, setSelectedRunId] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmOpen, setConfirmOpen] = useState(false);

  const candidate = candidates.find((r) => r.id === selectedRunId) ?? null;
  const m = candidate?.results?.primary_metric;
  const newValue = m ? candidate!.results!.holdout.metrics[m] : undefined;
  const currentValue = m ? currentRun?.results?.holdout.metrics[m] : undefined;
  const lowerBetter = m ? LOWER_BETTER.has(m) : false;
  const delta =
    newValue !== undefined && currentValue !== undefined ? newValue - currentValue : null;
  const improved = delta === null ? null : lowerBetter ? delta < 0 : delta > 0;

  const currentLabel =
    currentRun?.results?.methodology.display_name ?? currentRun?.plan?.methodology_id ?? "the currently serving run";
  const candidateLabel = candidate?.results?.methodology.display_name ?? "the selected run";

  async function handleConfirm() {
    if (!selectedRunId) return;
    setBusy(true);
    setError(null);
    try {
      await onPromote(selectedRunId);
      setConfirmOpen(false);
    } catch (e) {
      setError(extractErrorDetail(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="border-t border-zinc-800 pt-4">
      <Disclosure tone="label" summary="Switch serving model">
        <div className="space-y-2.5">
          <p className="measure text-label text-zinc-400">
            Point this deployment at a different completed run — not the one you&rsquo;re currently
            viewing. To serve the run you&rsquo;re looking at now, use the promote button on that run
            instead.
          </p>
          <select
            value={selectedRunId}
            onChange={(e) => setSelectedRunId(e.target.value)}
            className="focus-ring w-full rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 text-body text-zinc-300 focus:border-accent-edge"
          >
            <option value="">Select a completed run…</option>
            {candidates.map((r) => {
              const rm = r.results!.primary_metric;
              return (
                <option key={r.id} value={r.id}>
                  {r.results!.methodology.display_name} · {METRIC_LABELS[rm] ?? rm}{" "}
                  {fmt(r.results!.holdout.metrics[rm])} · {new Date(r.created_at).toLocaleDateString()}
                </option>
              );
            })}
          </select>

          {m && currentValue !== undefined && newValue !== undefined && (
            <div className="text-label" style={{ color: improved ? GOOD : BAD }}>
              {METRIC_LABELS[m] ?? m}: {fmt(currentValue)} → {fmt(newValue)} {improved ? "▲" : "▼"}
            </div>
          )}

          {error && (
            <div className="rounded-lg bg-alarm-wash px-3 py-2 text-label text-alarm">
              {error}
            </div>
          )}

          <button
            onClick={() => setConfirmOpen(true)}
            disabled={!selectedRunId || busy}
            className="focus-ring-panel rounded-lg px-4 py-2 text-body font-medium text-zinc-300 transition-colors hover:bg-zinc-800 hover:text-accent disabled:opacity-40"
          >
            {busy ? "Switching…" : "Switch"}
          </button>
        </div>
      </Disclosure>

      <ConfirmDialog
        open={confirmOpen}
        title="Switch serving model"
        body={
          <div className="space-y-2">
            <p>
              <span className="text-zinc-100">{currentLabel}</span> is currently serving this
              endpoint. Confirming will switch to{" "}
              <span className="text-zinc-100">{candidateLabel}</span>. Callers of the endpoint will
              immediately receive predictions from the new model.
            </p>
            {m && currentValue !== undefined && newValue !== undefined && (
              <p style={{ color: improved ? GOOD : BAD }}>
                {METRIC_LABELS[m] ?? m}: {fmt(currentValue)} → {fmt(newValue)} {improved ? "▲" : "▼"}
              </p>
            )}
          </div>
        }
        confirmLabel="Switch"
        busy={busy}
        onConfirm={handleConfirm}
        onCancel={() => {
          if (!busy) setConfirmOpen(false);
        }}
      />
    </div>
  );
}

function LiveTester({
  deployment,
  onPredicted,
  active,
}: {
  deployment: Deployment;
  onPredicted: () => void;
  active: boolean;
}) {
  const [text, setText] = useState(
    JSON.stringify({ records: [deployment.contract.example_record] }, null, 2),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<PredictResponse | null>(null);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const parsed = JSON.parse(text);
      const records = parsed.records;
      if (!Array.isArray(records)) throw new Error("Expected a JSON object with a `records` array.");
      const res = await api.predictDeployment(deployment.id, records);
      setResult(res);
      onPredicted();
    } catch (e) {
      setError(extractErrorDetail(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-2">
      <textarea
        value={text}
        onChange={(e) => setText(e.target.value)}
        rows={8}
        spellCheck={false}
        className="focus-ring w-full resize-y rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-300 focus:border-accent-edge"
      />
      <div className="flex items-center justify-between">
        <button
          onClick={run}
          disabled={busy || !active}
          className="focus-ring-panel rounded-lg px-4 py-2 text-body font-medium text-zinc-200 transition-colors hover:bg-zinc-800 hover:text-accent disabled:opacity-40"
        >
          {busy ? "Running…" : "Run prediction"}
        </button>
        {!active && (
          <span className="text-label text-zinc-400">Deployment is stopped — enable it to run predictions.</span>
        )}
      </div>
      {error && (
        <div className="rounded-lg bg-alarm-wash px-3 py-2 text-label text-alarm">
          {error}
        </div>
      )}
      {result && (
        <div className="rounded-lg bg-zinc-950/40 px-3 py-2.5">
          <h4 className="mb-1.5 text-label font-medium uppercase tracking-wide text-zinc-400">
            Response
          </h4>
          <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-xs text-zinc-300">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export default function DeploymentCard({
  deployment,
  currentRun,
  candidates,
  onPromote,
  onSetStatus,
}: {
  deployment: Deployment;
  currentRun?: Run | null;
  candidates?: Run[];
  onPromote?: (runId: string) => Promise<void>;
  onSetStatus?: (deploymentId: string, status: "active" | "disabled") => Promise<void>;
}) {
  const { contract } = deployment;
  const [toggling, setToggling] = useState(false);
  const isActive = deployment.status === "active";
  const [statsKey, setStatsKey] = useState(0);

  // The stored `deployment.name` is a snapshot from whenever this deployment
  // was first created — promotion never updates it, so it can actively
  // misstate what's currently serving. The currently-serving run's own
  // methodology is the ground truth for identity; fall back only when that
  // run (or its results) isn't available to us.
  const servingLabel =
    currentRun?.results?.methodology.display_name ??
    currentRun?.plan?.methodology_id ??
    deployment.name;
  const showStoredName = deployment.name && deployment.name !== servingLabel;

  async function toggleStatus() {
    setToggling(true);
    try {
      await onSetStatus?.(deployment.id, isActive ? "disabled" : "active");
    } catch {
      // Leave the status unchanged if the request fails.
    } finally {
      setToggling(false);
    }
  }

  const featureCount = contract.feature_columns.length;

  return (
    <div className="space-y-5">
      {/* Identity and live status — always visible, never behind a click. This
          is what someone opens the Deploy tab to check: what's serving, is it
          running, which version, and the control to stop/enable it. */}
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-zinc-800 pb-3">
        <div className="flex min-w-0 flex-col gap-0.5">
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-title font-medium text-zinc-100">{servingLabel}</span>
            <span
              className={`rounded px-2 py-0.5 text-label font-medium ${
                isActive ? "bg-accent-wash text-accent" : "bg-zinc-800 text-zinc-400"
              }`}
            >
              {isActive ? "active" : "stopped"}
            </span>
            <span className="text-label text-zinc-400">v{deployment.version}</span>
            {isActive && (
              <span className="flex items-center gap-1 text-label font-medium text-accent">
                <span className="h-1.5 w-1.5 rounded-full bg-accent" />
                LIVE
              </span>
            )}
          </div>
          {showStoredName && (
            <span className="text-label text-zinc-400">deployment name: {deployment.name}</span>
          )}
        </div>
        <button
          onClick={toggleStatus}
          disabled={toggling}
          className={`focus-ring-panel rounded-lg px-3 py-1.5 text-label font-medium transition-colors disabled:opacity-40 ${
            isActive
              ? "text-zinc-300 hover:bg-zinc-800 hover:text-alarm"
              : "text-zinc-300 hover:bg-zinc-800 hover:text-accent"
          }`}
        >
          {toggling ? "…" : isActive ? "Stop deployment" : "Enable deployment"}
        </button>
      </div>

      <div>
        <Disclosure
          tone="label"
          summary="Input contract"
          meta={`${featureCount} feature${featureCount === 1 ? "" : "s"}`}
        >
          <div className="mb-2 overflow-x-auto">
            <table className="w-full text-left text-label" style={{ fontVariantNumeric: "tabular-nums" }}>
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-400">
                  <th className="px-3 py-2 font-normal">Column</th>
                  <th className="px-3 py-2 font-normal">Type</th>
                  <th className="px-3 py-2 font-normal">Example</th>
                </tr>
              </thead>
              <tbody>
                {contract.feature_columns.map((f) => (
                  <tr key={f.name} className="border-b border-zinc-800/50 last:border-0">
                    <td className="px-3 py-1.5 font-mono text-xs text-zinc-300">{f.name}</td>
                    <td className="px-3 py-1.5 font-mono text-xs text-zinc-400">{f.dtype}</td>
                    <td className="px-3 py-1.5 font-mono text-xs text-zinc-400">{String(f.example)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="measure mb-1 text-label text-zinc-400">
            Target <span className="font-mono text-xs text-zinc-400">{contract.target_column}</span> ·{" "}
            {contract.task_type.replace(/_/g, " ")}
          </p>
          <pre className="overflow-x-auto whitespace-pre-wrap rounded-lg border border-zinc-800 bg-zinc-950 px-3 py-2 font-mono text-xs text-zinc-400">
            {JSON.stringify(contract.example_record, null, 2)}
          </pre>
        </Disclosure>
      </div>

      <div>
        <h4 className="mb-2 text-label font-medium uppercase tracking-wide text-zinc-400">
          Live tester
        </h4>
        <LiveTester
          deployment={deployment}
          active={isActive}
          onPredicted={() => setStatsKey((k) => k + 1)}
        />
      </div>

      <div>
        <h4 className="mb-2 text-label font-medium uppercase tracking-wide text-zinc-400">
          Serving stats
        </h4>
        <StatsPanel key={`${deployment.version}-${statsKey}`} deploymentId={deployment.id} />
      </div>

      {candidates && candidates.length > 0 && onPromote && (
        <PromoteSection
          currentRun={currentRun ?? null}
          candidates={candidates}
          onPromote={onPromote}
        />
      )}
    </div>
  );
}
