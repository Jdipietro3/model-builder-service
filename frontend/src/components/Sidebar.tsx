"use client";

/**
 * The persistent left rail, with two views the user flips between:
 *
 *   "projects" — every project, plus New project
 *   "project"  — the open project's nav (title, model dropdown, tabs)
 *
 * The project view is passed in as `nav` rather than rendered here, because it
 * needs ProjectProvider state and this component is also used on `/`, where no
 * such provider exists. projects/[id]/layout.tsx supplies <ProjectNav /> from
 * inside the provider; `/` passes nothing and the rail stays on the list.
 *
 * Flipping to the list does NOT navigate away — you can browse projects while
 * staying in the one you have open, which is the behaviour the whiteboard
 * sketch calls for.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useProjects } from "@/lib/projects-context";

export default function Sidebar({ nav }: { nav?: React.ReactNode }) {
  const { projects, error } = useProjects();
  const router = useRouter();
  // Seeded from whether a project is open, then owned by the user: opening a
  // project flips to its nav, and the back control flips back to the list.
  const [view, setView] = useState<"projects" | "project">(nav ? "project" : "projects");

  // Opening a different project (or landing on `/`) re-seeds the view. Without
  // this, flipping to the list and then picking a project would leave the rail
  // showing the list of a project you already navigated away from.
  useEffect(() => {
    setView(nav ? "project" : "projects");
  }, [nav]);

  return (
    <nav
      aria-label="Projects"
      className="flex w-64 shrink-0 flex-col border-r border-zinc-800 bg-zinc-950"
    >
      {view === "project" && nav ? (
        <>
          <div className="border-b border-zinc-800 p-3">
            <button
              onClick={() => setView("projects")}
              className="focus-ring flex w-full items-center gap-1.5 rounded px-1 py-1 text-left text-label text-zinc-400 transition-colors hover:text-zinc-200"
            >
              <span aria-hidden="true">←</span> All projects
            </button>
          </div>
          <div className="min-h-0 flex-1 overflow-y-auto">{nav}</div>
        </>
      ) : (
        <>
          <div className="border-b border-zinc-800 p-3">
            <Link
              href="/"
              className="focus-ring flex w-full items-center gap-2 rounded-lg border border-zinc-800 px-3 py-2 text-body font-medium text-zinc-200 transition-colors hover:border-emerald-700 hover:text-emerald-400"
            >
              <span aria-hidden="true">+</span> New project
            </Link>
          </div>

          <div className="min-h-0 flex-1 overflow-y-auto p-2">
            <h2 className="px-2 py-1.5 text-label uppercase tracking-wide text-zinc-400">
              Projects
            </h2>

            {error && <p className="px-2 py-2 text-label text-red-300">{error}</p>}

            {projects === null && !error && (
              <div className="space-y-1.5 p-1" aria-hidden="true">
                <div className="h-8 animate-pulse rounded bg-zinc-900" />
                <div className="h-8 animate-pulse rounded bg-zinc-900/60" />
              </div>
            )}

            {projects?.length === 0 && (
              <p className="px-2 py-2 text-label text-zinc-400">
                No projects yet. Start one above.
              </p>
            )}

            <ul className="space-y-0.5">
              {projects?.map((p) => (
                <li key={p.id}>
                  <button
                    onClick={() => {
                      setView("project");
                      router.push(`/projects/${p.id}`);
                    }}
                    className="focus-ring-panel block w-full truncate rounded px-2 py-1.5 text-left text-body text-zinc-300 transition-colors hover:bg-zinc-900 hover:text-zinc-100"
                    title={p.name}
                  >
                    {p.name}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </nav>
  );
}
