"use client";

/**
 * Deploy tab: the live endpoint, its request contract, and how to call it.
 *
 * DeploymentCard (drift stats, version history, promote) moves here from the
 * Model section, joined by the integration detail an engineer actually needs to
 * wire this up — the URL, the JSON shape, a curl they can paste, and now real
 * API key management (create/list/revoke) instead of the old "no auth yet"
 * notice — the predict endpoint requires a bearer key as of the backend's
 * /deployments/{id}/keys routes.
 */

import { useCallback, useEffect, useState } from "react";
import { api, API_BASE, CreatedDeploymentKey, Deployment, DeploymentKey, Methodology, Run } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { extractErrorDetail } from "@/lib/errors";
import { runLabel } from "@/lib/run-label";
import DeploymentCard from "@/components/cards/DeploymentCard";
import EmptyTab from "@/components/tabs/EmptyTab";
import Disclosure from "@/components/Disclosure";

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      onClick={async () => {
        try {
          await navigator.clipboard.writeText(text);
          setCopied(true);
          setTimeout(() => setCopied(false), 1500);
        } catch {
          // Clipboard can be blocked (insecure origin, permissions). The snippet
          // is selectable on screen either way, so fail quietly rather than alarm.
        }
      }}
      className="focus-ring-panel rounded px-2 py-1 text-label text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-accent"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

/**
 * Endpoint contract (URL, body shape, curl) plus API key management for one
 * deployment. Pulled out of the deployments.map() below because key state is
 * per-deployment and hooks can't live inside a loop body.
 */
function EndpointPanel({ deployment }: { deployment: Deployment }) {
  const [keys, setKeys] = useState<DeploymentKey[] | null>(null);
  const [keysError, setKeysError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  // The one moment the full secret is ever available client-side — cleared
  // the instant its own key is revoked so a stale secret can't linger on
  // screen looking usable after the backend has forgotten it.
  const [justCreated, setJustCreated] = useState<CreatedDeploymentKey | null>(null);

  const loadKeys = useCallback(async () => {
    try {
      const list = await api.listDeploymentKeys(deployment.id);
      setKeys(list);
      setKeysError(null);
    } catch (e) {
      setKeysError(extractErrorDetail(e));
    }
  }, [deployment.id]);

  useEffect(() => {
    loadKeys();
  }, [loadKeys]);

  async function handleCreate() {
    setCreating(true);
    setKeysError(null);
    try {
      const created = await api.createDeploymentKey(deployment.id);
      setJustCreated(created);
      await loadKeys();
    } catch (e) {
      setKeysError(extractErrorDetail(e));
    } finally {
      setCreating(false);
    }
  }

  async function handleRevoke(keyId: string) {
    setRevokingId(keyId);
    setKeysError(null);
    try {
      await api.deleteDeploymentKey(deployment.id, keyId);
      if (justCreated?.id === keyId) setJustCreated(null);
      await loadKeys();
    } catch (e) {
      setKeysError(extractErrorDetail(e));
    } finally {
      setRevokingId(null);
    }
  }

  const url = `${API_BASE}/deployments/${deployment.id}/predict`;
  const body = JSON.stringify({ records: [deployment.contract.example_record] }, null, 2);
  // The snippet uses the real secret only in the render right after creation
  // — the sole moment the backend will ever hand it back. Every other render
  // falls back to a placeholder so this box never reads as a live credential.
  const authValue = justCreated ? justCreated.key : "mb_...";
  const curl = `curl -X POST ${url} \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${authValue}" \\\n  -d '${JSON.stringify({ records: [deployment.contract.example_record] })}'`;

  // justCreated holds the only copy of a full API secret the backend will ever
  // return. If the disclosure is forced open here and the user later collapses
  // it by hand, that's fine — they've seen and (presumably) copied it. But it
  // must never start collapsed while a secret is waiting to be read, so the
  // open state is controlled and re-synced whenever justCreated changes.
  const [keysOpen, setKeysOpen] = useState(false);
  useEffect(() => {
    if (justCreated) setKeysOpen(true);
  }, [justCreated]);

  const keysSummary =
    keys === null && !keysError ? "loading…" : keys ? `${keys.length} key${keys.length === 1 ? "" : "s"}` : "none yet";

  return (
    <section className="space-y-4">
      <div className="border-b border-zinc-800 pb-4">
        <h3 className="mb-2 text-title font-medium text-zinc-100">Using this endpoint</h3>
        <p className="measure mb-3 text-label leading-relaxed text-zinc-400">
          A prediction endpoint takes one record — shaped like the rows this model trained on —
          and returns the model&rsquo;s answer for that record. Nothing more happens on the way:
          no lookup, no rule engine, just the model applied to what you sent. What the returned
          value means (a class, a probability, a forecasted number) depends on the task type, and
          how much to trust it depends on the metrics on the Metrics tab — the endpoint itself
          can&rsquo;t tell you that.
        </p>
        <ol className="measure list-decimal space-y-1 pl-5 text-label leading-relaxed text-zinc-300">
          <li>Create an API key below.</li>
          <li>Copy it now — the full key is shown only once.</li>
          <li>Send a POST request to the endpoint with one record in the JSON body.</li>
          <li>Read the prediction back out of the response.</li>
        </ol>
      </div>

      <Disclosure tone="title" summary="Calling this endpoint">
        <div className="space-y-4">
          <p className="measure text-label leading-relaxed text-zinc-400">
            Requests require an API key. Create one below and send it as{" "}
            <code className="font-mono text-xs text-zinc-300">Authorization: Bearer &lt;key&gt;</code>.
          </p>

          <dl className="space-y-2 text-label">
            <div>
              <dt className="mb-1 uppercase tracking-wide text-zinc-400">Endpoint</dt>
              <dd className="flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded bg-zinc-950 px-2 py-1 font-mono text-zinc-300">
                  POST {url}
                </code>
                <CopyButton text={url} />
              </dd>
            </div>
            <div>
              <dt className="mb-1 uppercase tracking-wide text-zinc-400">
                Request body ({deployment.contract.feature_columns.length} feature
                {deployment.contract.feature_columns.length === 1 ? "" : "s"})
              </dt>
              <dd>
                <pre className="overflow-x-auto rounded bg-zinc-950 p-2 font-mono text-xs leading-relaxed text-zinc-300">
                  {body}
                </pre>
              </dd>
            </div>
          </dl>

          <div>
            <div className="flex items-center justify-between gap-2">
              <span className="text-label uppercase tracking-wide text-zinc-400">curl</span>
              <CopyButton text={curl} />
            </div>
            <pre className="mt-1 overflow-x-auto rounded bg-zinc-950 p-2 font-mono text-xs leading-relaxed text-zinc-300">
              {curl}
            </pre>
          </div>
        </div>
      </Disclosure>

      <Disclosure
        tone="label"
        summary="API keys"
        meta={keysSummary}
        open={keysOpen}
        onOpenChange={setKeysOpen}
        className="border-t border-zinc-800 pt-4"
      >
        <div className="space-y-2">
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating}
            className="focus-ring-panel rounded-lg bg-accent px-3 py-1.5 text-label font-medium text-accent-ink transition-colors hover:bg-accent-bright disabled:opacity-40"
          >
            {creating ? "Creating…" : "Create key"}
          </button>
        </div>

        {keysError && (
          <div className="fade-in flex items-start gap-2 rounded-lg bg-alarm-wash px-3 py-2 text-label text-alarm">
            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-alarm" />
            <span>{keysError}</span>
          </div>
        )}

        {justCreated && (
          <div className="fade-in space-y-2 rounded-lg border border-accent-edge bg-accent-wash px-3 py-2.5">
            <p className="text-label text-accent-bright">
              Copy this key now — it will not be shown again once you navigate away.
            </p>
            <div className="flex items-center gap-2">
              <code className="min-w-0 flex-1 truncate rounded bg-zinc-950 px-2 py-1 font-mono text-xs text-zinc-100">
                {justCreated.key}
              </code>
              <CopyButton text={justCreated.key} />
            </div>
          </div>
        )}

        {keys === null && !keysError && <p className="text-label text-zinc-400">Loading keys…</p>}
        {keys?.length === 0 && (
          <p className="text-label text-zinc-400">
            No keys yet. Create one to call this endpoint.
          </p>
        )}
        {keys && keys.length > 0 && (
          <ul className="divide-y divide-zinc-800/50">
            {keys.map((k) => (
              <li key={k.id} className="flex items-center justify-between gap-2 py-2">
                <div className="min-w-0">
                  <div className="font-mono text-xs text-zinc-300">{k.prefix}…</div>
                  <div className="text-label text-zinc-400">
                    Created {new Date(k.created_at).toLocaleDateString()}
                    {" · "}
                    {k.last_used_at
                      ? `last used ${new Date(k.last_used_at).toLocaleDateString()}`
                      : "never used"}
                  </div>
                </div>
                <button
                  type="button"
                  onClick={() => handleRevoke(k.id)}
                  disabled={revokingId === k.id}
                  className="focus-ring-panel shrink-0 rounded px-2 py-1 text-label text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-alarm disabled:opacity-40"
                >
                  {revokingId === k.id ? "Revoking…" : "Revoke"}
                </button>
              </li>
            ))}
          </ul>
        )}
        </div>
      </Disclosure>
    </section>
  );
}

/**
 * The deploy control shown when the project has no deployment yet. One
 * primary-per-view: a lone deployable run gets a single button (no picker for
 * a choice of one), more than one gets a select alongside it. Once a
 * deployment exists this control disappears for good — promoting a different
 * run onto it is DeploymentCard's job, not a second "create deployment" path.
 */
function DeployControl({
  runs,
  methodologies,
  onDeploy,
}: {
  runs: Run[];
  methodologies: Methodology[];
  onDeploy: (runId: string) => Promise<void>;
}) {
  const sorted = [...runs].sort(
    (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime(),
  );
  const [selectedId, setSelectedId] = useState(sorted[0]?.id ?? "");
  const [deploying, setDeploying] = useState(false);
  const selected = sorted.find((r) => r.id === selectedId) ?? sorted[0];

  async function handleClick() {
    if (!selected) return;
    setDeploying(true);
    try {
      await onDeploy(selected.id);
    } finally {
      setDeploying(false);
    }
  }

  const buttonLabel = deploying ? "Deploying…" : `Deploy ${runLabel(selected, methodologies)}`;
  const button = (
    <button
      type="button"
      onClick={handleClick}
      disabled={deploying || !selected}
      className="focus-ring rounded-lg bg-accent px-4 py-2 text-body font-medium text-accent-ink transition-colors hover:bg-accent-bright disabled:opacity-40"
    >
      {buttonLabel}
    </button>
  );

  if (sorted.length === 1) return button;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <select
        value={selectedId}
        onChange={(e) => setSelectedId(e.target.value)}
        className="focus-ring-panel rounded-md border border-zinc-700 bg-zinc-900 px-2 py-1.5 text-label text-zinc-200 focus:border-accent-edge"
      >
        {sorted.map((r) => (
          <option key={r.id} value={r.id}>
            {runLabel(r, methodologies)}
          </option>
        ))}
      </select>
      {button}
    </div>
  );
}

export default function DeployTab() {
  const { runs, runStates, methodologies, deployments, handleDeploy, handlePromote, handleSetDeploymentStatus } =
    useProject();

  if (deployments.length === 0) {
    // Mirrors ModelTab's canDeploy predicate exactly — forecasting runs don't
    // fit the single-record predict contract, so they're never offered here.
    const deployable = runs
      .map((r): Run => ({ ...r, results: runStates[r.id]?.results ?? r.results }))
      .filter(
        (r) =>
          (runStates[r.id]?.status ?? r.status) === "completed" &&
          r.plan.task_type !== "forecasting" &&
          r.results != null,
      );

    return (
      <section className="space-y-3">
        <h2 className="text-headline font-semibold text-zinc-100">Deploy</h2>
        {deployable.length === 0 ? (
          <EmptyTab
            title="Nothing deployed yet"
            body="Once a run finishes training, deploy it here to get a live prediction endpoint."
          />
        ) : (
          <DeployControl runs={deployable} methodologies={methodologies} onDeploy={handleDeploy} />
        )}
      </section>
    );
  }

  return (
    <section className="space-y-4">
      <h2 className="text-headline font-semibold text-zinc-100">Deploy</h2>

      {deployments.map((d) => {
        // Shallow-copy in live results (from runStates) without mutating the
        // original run objects.
        const resolve = (r: Run): Run => ({ ...r, results: runStates[r.id]?.results ?? r.results });
        const currentRun = runs.find((r) => r.id === d.run_id);
        const resolvedCurrentRun = currentRun ? resolve(currentRun) : null;
        const candidates = runs
          .map(resolve)
          .filter(
            (r) =>
              (runStates[r.id]?.status ?? r.status) === "completed" &&
              r.plan.task_type !== "forecasting" &&
              r.plan.target_column === d.contract.target_column &&
              r.plan.task_type === d.contract.task_type &&
              r.id !== d.run_id &&
              r.results != null,
          );

        return (
          <div key={d.id} className="space-y-5 border-t border-zinc-800 pt-5 first:border-0 first:pt-0">
            <DeploymentCard
              deployment={d}
              currentRun={resolvedCurrentRun}
              candidates={candidates}
              onPromote={async (runId) => {
                await handlePromote(d.id, runId);
              }}
              onSetStatus={handleSetDeploymentStatus}
            />

            <EndpointPanel deployment={d} />
          </div>
        );
      })}
    </section>
  );
}
