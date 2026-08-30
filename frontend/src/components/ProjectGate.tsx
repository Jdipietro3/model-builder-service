"use client";

/**
 * Holds the tab content back until the project has actually loaded.
 *
 * Without this, a deep link straight to /metrics or /deploy renders the tab
 * against empty state for one paint and tells the user "no results yet" about
 * a run that finished days ago. Splitting the old single page into five routes
 * made every tab independently deep-linkable, so every tab inherited that
 * flash; gating once here fixes all of them rather than five copies of the
 * same guard.
 *
 * The chat rail deliberately sits OUTSIDE this gate — it has its own empty
 * state and there is no reason to withhold it.
 */

import { useProject } from "@/lib/project-context";

export default function ProjectGate({ children }: { children: React.ReactNode }) {
  const { loading, loadError } = useProject();

  if (loadError) {
    return (
      <div className="rounded-lg border border-red-900 bg-red-950/50 px-6 py-4 text-red-300">
        Failed to load project: {loadError}
      </div>
    );
  }

  if (loading) {
    return (
      <div className="space-y-3" aria-busy="true" aria-live="polite">
        <span className="sr-only">Loading project…</span>
        <div className="h-7 w-40 animate-pulse rounded bg-zinc-900" aria-hidden="true" />
        <div className="h-32 animate-pulse rounded-lg bg-zinc-900/60" aria-hidden="true" />
        <div className="h-32 animate-pulse rounded-lg bg-zinc-900/40" aria-hidden="true" />
      </div>
    );
  }

  return <>{children}</>;
}
