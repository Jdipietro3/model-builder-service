"use client";

/**
 * The rail's project view: title, model selector, tab list.
 *
 * Rendered by projects/[id]/layout.tsx from inside ProjectProvider, then handed
 * to <Sidebar nav={...} />. The model <select> writes the shared selectedRunId,
 * which every tab reads — that ambient selection is what lets Score and Metrics
 * exist as their own tabs without each growing a second run picker.
 */

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useProject } from "@/lib/project-context";
import { runLabel, STATUS_DOT } from "@/lib/run-label";

const TABS = [
  { slug: "model", label: "Model" },
  { slug: "data", label: "Data" },
  { slug: "metrics", label: "Metrics" },
  { slug: "score", label: "Score" },
  { slug: "deploy", label: "Deploy" },
] as const;

export default function ProjectNav() {
  const {
    projectId,
    project,
    orderedRuns,
    selectedRun,
    setSelectedRunId,
    methodologies,
    runStates,
    deployments,
  } = useProject();
  const pathname = usePathname();

  const liveRunId = deployments[0]?.run_id ?? null;
  const selectedStatus = selectedRun
    ? (runStates[selectedRun.id]?.status ?? selectedRun.status)
    : null;

  return (
    <div className="flex flex-col gap-4 p-3">
      <h1 className="px-1 text-title font-semibold text-zinc-100" title={project?.name}>
        {project?.name ?? "…"}
      </h1>

      <div>
        <label
          htmlFor="model-select"
          className="mb-1.5 block px-1 text-label uppercase tracking-wide text-zinc-400"
        >
          Model
        </label>
        {orderedRuns.length === 0 ? (
          <p className="px-1 text-label text-zinc-400">None yet</p>
        ) : (
          <div className="flex items-center gap-2">
            {selectedStatus && (
              <span
                aria-hidden="true"
                className={`h-1.5 w-1.5 shrink-0 rounded-full ${
                  STATUS_DOT[selectedStatus] ?? "bg-zinc-500"
                }`}
              />
            )}
            <select
              id="model-select"
              value={selectedRun?.id ?? ""}
              onChange={(e) => setSelectedRunId(e.target.value)}
              className="focus-ring min-w-0 flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-2 py-1.5 text-body text-zinc-200 outline-none focus:border-emerald-600"
            >
              {orderedRuns.map((r) => (
                <option key={r.id} value={r.id}>
                  {runLabel(r, methodologies)}
                  {r.id === liveRunId ? " · live" : ""}
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <ul className="space-y-0.5">
        {TABS.map((t) => {
          const href = `/projects/${projectId}/${t.slug}`;
          const active = pathname === href;
          return (
            <li key={t.slug}>
              <Link
                href={href}
                aria-current={active ? "page" : undefined}
                className={`focus-ring-panel block rounded px-2 py-1.5 text-body transition-colors ${
                  active
                    ? "bg-zinc-900 font-medium text-emerald-400"
                    : "text-zinc-300 hover:bg-zinc-900 hover:text-zinc-100"
                }`}
              >
                {t.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}
