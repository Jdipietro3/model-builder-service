"use client";

/**
 * Deploy tab: the live endpoint, its request contract, and how to call it.
 *
 * DeploymentCard (drift stats, version history, promote) moves here from the
 * Model section, joined by the integration detail an engineer actually needs to
 * wire this up — the URL, the JSON shape, and a curl they can paste.
 *
 * NO API KEY. The predict endpoint is currently unauthenticated: there is no key
 * concept anywhere in the backend models. Rather than imply a security boundary
 * that does not exist, this tab says so plainly. Adding real keys is backend
 * work, tracked separately.
 */

import { useState } from "react";
import { API_BASE, Run } from "@/lib/api";
import { useProject } from "@/lib/project-context";
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

        const url = `${API_BASE}/deployments/${d.id}/predict`;
        const body = JSON.stringify(
          { records: [d.contract.example_record] },
          null,
          2,
        );
        const curl = `curl -X POST ${url} \\\n  -H "Content-Type: application/json" \\\n  -d '${JSON.stringify({ records: [d.contract.example_record] })}'`;

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

            <div className="rounded-lg border border-zinc-800 bg-zinc-900/60 p-4">
              <div className="mb-3 flex items-center justify-between gap-2">
                <h3 className="text-title font-medium text-zinc-100">Calling this endpoint</h3>
                <span className="rounded bg-zinc-800 px-1.5 py-0.5 text-label text-zinc-400">
                  No auth
                </span>
              </div>

              <p className="measure mb-3 text-label leading-relaxed text-zinc-400">
                This endpoint is open — anyone who can reach the host can call it. There is no API
                key yet, so treat the URL itself as the only thing standing between your model and
                the network, and do not expose it publicly.
              </p>

              <dl className="mb-3 space-y-2 text-label">
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
                    Request body ({d.contract.feature_columns.length} feature
                    {d.contract.feature_columns.length === 1 ? "" : "s"})
                  </dt>
                  <dd>
                    <pre className="overflow-x-auto rounded bg-zinc-950 p-2 font-mono text-xs leading-relaxed text-zinc-300">
                      {body}
                    </pre>
                  </dd>
                </div>
              </dl>

              <div className="flex items-center justify-between gap-2">
                <span className="text-label uppercase tracking-wide text-zinc-400">curl</span>
                <CopyButton text={curl} />
              </div>
              <pre className="mt-1 overflow-x-auto rounded bg-zinc-950 p-2 font-mono text-xs leading-relaxed text-zinc-300">
                {curl}
              </pre>
            </div>
          </div>
        );
      })}
    </section>
  );
}
