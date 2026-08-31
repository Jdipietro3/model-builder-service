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
import { api, API_BASE, CreatedDeploymentKey, Deployment, DeploymentKey, Run } from "@/lib/api";
import { useProject } from "@/lib/project-context";
import { extractErrorDetail } from "@/lib/errors";
import DeploymentCard from "@/components/cards/DeploymentCard";
import EmptyTab from "@/components/tabs/EmptyTab";

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
      className="focus-ring-panel rounded border border-zinc-700 px-2 py-0.5 text-label text-zinc-400 transition-colors hover:border-emerald-600 hover:text-emerald-400"
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

  return (
    <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
      <h3 className="mb-3 text-title font-medium text-zinc-100">Calling this endpoint</h3>

      <p className="measure mb-3 text-label leading-relaxed text-zinc-400">
        Requests require an API key. Create one below and send it as{" "}
        <code className="font-mono text-xs text-zinc-300">Authorization: Bearer &lt;key&gt;</code>.
      </p>

      <dl className="mb-4 space-y-2 text-label">
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

      <div className="mb-4">
        <div className="flex items-center justify-between gap-2">
          <span className="text-label uppercase tracking-wide text-zinc-400">curl</span>
          <CopyButton text={curl} />
        </div>
        <pre className="mt-1 overflow-x-auto rounded bg-zinc-950 p-2 font-mono text-xs leading-relaxed text-zinc-300">
          {curl}
        </pre>
      </div>

      <div className="border-t border-zinc-800 pt-4">
        <div className="mb-2 flex items-center justify-between gap-2">
          <h4 className="text-label uppercase tracking-wide text-zinc-400">API keys</h4>
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating}
            className="focus-ring-panel rounded border border-zinc-700 px-2 py-0.5 text-label text-zinc-300 transition-colors hover:border-emerald-600 hover:text-emerald-400 disabled:opacity-40"
          >
            {creating ? "Creating…" : "Create key"}
          </button>
        </div>

        {keysError && (
          <div className="fade-in mb-2 flex items-start gap-2 rounded-lg border border-red-900 bg-red-950/50 px-3 py-2 text-label text-red-300">
            <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" />
            <span>{keysError}</span>
          </div>
        )}

        {justCreated && (
          <div className="fade-in mb-2 space-y-2 rounded-lg border border-emerald-800 bg-emerald-950/30 px-3 py-2.5">
            <p className="text-label text-emerald-300">
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
          <ul className="divide-y divide-zinc-800 overflow-hidden rounded-lg border border-zinc-800">
            {keys.map((k) => (
              <li
                key={k.id}
                className="flex items-center justify-between gap-2 bg-zinc-950/40 px-3 py-2"
              >
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
                  className="focus-ring-panel shrink-0 rounded border border-zinc-700 px-2 py-0.5 text-label text-zinc-400 transition-colors hover:border-red-600 hover:text-red-400 disabled:opacity-40"
                >
                  {revokingId === k.id ? "Revoking…" : "Revoke"}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export default function DeployTab() {
  const { runs, runStates, deployments, handlePromote, handleSetDeploymentStatus } = useProject();

  if (deployments.length === 0) {
    return (
      <section className="space-y-3">
        <h2 className="text-headline font-semibold text-zinc-100">Deploy</h2>
        <EmptyTab
          title="Nothing deployed yet"
          body="Once a run completes, use Deploy this model on the Model tab. You get a prediction endpoint backed by that exact model."
        />
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
          <div key={d.id} className="space-y-4">
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
