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
 *
 * The rail also collapses to a 56px icon strip. Collapsed state is owned here
 * (not in `nav`, which this component treats as an opaque child) and handed
 * down through RailCollapsedProvider so ProjectNav — built by a server
 * component that cannot pass it a `collapsed` prop directly — can still render
 * its own collapsed layout.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useProjects } from "@/lib/projects-context";
import MetisMark from "@/components/MetisMark";
import { RailCollapsedProvider } from "@/components/rail-context";
import { ListIcon, PlusIcon, UserIcon, SignOutIcon, PanelToggleIcon } from "@/components/RailIcons";

const COLLAPSED_STORAGE_KEY = "metis:rail-collapsed";

function readStoredCollapsed(): boolean {
  try {
    return window.localStorage.getItem(COLLAPSED_STORAGE_KEY) === "1";
  } catch {
    return false;
  }
}

function writeStoredCollapsed(collapsed: boolean) {
  try {
    window.localStorage.setItem(COLLAPSED_STORAGE_KEY, collapsed ? "1" : "0");
  } catch {
    // Persistence is a decorative preference — storage throwing (private
    // browsing, quota, disabled storage) must never break the rail.
  }
}

export default function Sidebar({ nav }: { nav?: React.ReactNode }) {
  const { projects, error, user, userLoading } = useProjects();
  const router = useRouter();
  // Seeded from whether a project is open, then owned by the user: opening a
  // project flips to its nav, and the back control flips back to the list.
  const [view, setView] = useState<"projects" | "project">(nav ? "project" : "projects");
  const [signingOut, setSigningOut] = useState(false);
  // Seeded expanded so the server-rendered markup and the first client render
  // agree; the stored preference (if any) is only applied from an effect,
  // after hydration, never read during render.
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setCollapsed(readStoredCollapsed());
  }, []);

  useEffect(() => {
    writeStoredCollapsed(collapsed);
  }, [collapsed]);

  // Opening a different project (or landing on `/`) re-seeds the view. Without
  // this, flipping to the list and then picking a project would leave the rail
  // showing the list of a project you already navigated away from.
  useEffect(() => {
    setView(nav ? "project" : "projects");
  }, [nav]);

  async function handleSignOut() {
    setSigningOut(true);
    try {
      await api.logout();
    } catch {
      // Even a failed logout request should still land the user on /login —
      // there's no useful recovery from here, and staying signed in to a UI
      // that thinks it's logged out is worse than a redundant redirect.
    } finally {
      router.push("/login");
    }
  }

  return (
    <RailCollapsedProvider value={{ collapsed, setCollapsed }}>
      <nav
        aria-label="Projects"
        className={`flex shrink-0 flex-col overflow-hidden border-r border-zinc-800 bg-zinc-950 transition-[width] duration-150 ${
          collapsed ? "w-14" : "w-72"
        }`}
      >
        <div
          className={`flex shrink-0 items-center border-b border-zinc-800 py-3 ${
            collapsed ? "justify-center px-2" : "gap-1.5 px-4"
          }`}
        >
          <MetisMark size={16} className="text-accent" />
          {!collapsed && <span className="text-label font-medium text-zinc-300">Metis</span>}
        </div>

        {/* The toggle heads the column in both states, and sits in the header
            row when expanded — i.e. the same place on screen either way. Parked
            at the rail's foot while collapsed, it would move out from under the
            cursor that just collapsed it, and the control that undoes an action
            should not have to be hunted for. */}
        {view === "project" && nav ? (
          collapsed ? (
            <div className="flex min-h-0 flex-1 flex-col items-center gap-1 overflow-y-auto p-2">
              <RailToggle collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
              <button
                onClick={() => setView("projects")}
                aria-label="All projects"
                title="All projects"
                className="focus-ring-panel flex h-10 w-10 items-center justify-center rounded text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-100"
              >
                <ListIcon size={18} />
              </button>
              {nav}
            </div>
          ) : (
            <>
              <div className="flex shrink-0 items-center gap-1 border-b border-zinc-800 p-3">
                <button
                  onClick={() => setView("projects")}
                  className="focus-ring flex flex-1 items-center gap-1.5 rounded px-1 py-1 text-left text-label text-zinc-400 transition-colors hover:text-zinc-200"
                >
                  <span aria-hidden="true">←</span> All projects
                </button>
                <RailToggle collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
              </div>
              <div className="min-h-0 flex-1 overflow-y-auto">{nav}</div>
            </>
          )
        ) : collapsed ? (
          <div className="flex min-h-0 flex-1 flex-col items-center gap-1 overflow-y-auto p-2">
            <RailToggle collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
            <Link
              href="/"
              aria-label="New project"
              title="New project"
              className="focus-ring-panel flex h-10 w-10 items-center justify-center rounded text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-100"
            >
              <PlusIcon size={18} />
            </Link>
          </div>
        ) : (
          <>
            <div className="flex shrink-0 items-center gap-1 border-b border-zinc-800 p-3">
              <Link
                href="/"
                className="focus-ring flex flex-1 items-center gap-2 rounded-lg border border-zinc-800 px-3 py-2 text-body font-medium text-zinc-200 transition-colors hover:border-accent-edge hover:text-accent"
              >
                <span aria-hidden="true">+</span> New project
              </Link>
              <RailToggle collapsed={collapsed} onToggle={() => setCollapsed(!collapsed)} />
            </div>

            <div className="min-h-0 flex-1 overflow-y-auto p-2">
              <h2 className="px-2 py-1.5 text-label uppercase tracking-wide text-zinc-400">
                Projects
              </h2>

              {error && <p className="px-2 py-2 text-label text-alarm">{error}</p>}

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

        {/* Chrome for the whole rail, not for one view — rendered in both the
            project list and an open project's nav so there is always a way to
            reach /account or sign out. Sits outside either view's flex-1 scroll
            area so it stays pinned to the rail's bottom edge regardless of list
            or nav length. Gated on userLoading (not just `user`) so a signed-in
            visitor never sees this flash empty before the first /auth/me
            resolves. */}
        {!userLoading && user && (
          <div className="shrink-0 border-t border-zinc-800 p-3">
            {collapsed ? (
              <div className="flex flex-col items-center gap-1">
                <Link
                  href="/account"
                  aria-label="Account"
                  title={user.email}
                  className="focus-ring-panel flex h-10 w-10 items-center justify-center rounded text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-100"
                >
                  <UserIcon size={18} />
                </Link>
                <button
                  onClick={handleSignOut}
                  disabled={signingOut}
                  aria-label="Sign out"
                  title="Sign out"
                  className="focus-ring-panel flex h-10 w-10 items-center justify-center rounded text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-alarm disabled:opacity-40"
                >
                  <SignOutIcon size={18} />
                </button>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-2">
                <Link
                  href="/account"
                  className="focus-ring-panel min-w-0 flex-1 truncate rounded text-label text-zinc-400 transition-colors hover:text-zinc-200"
                  title={user.email}
                >
                  {user.email}
                </Link>
                <button
                  onClick={handleSignOut}
                  disabled={signingOut}
                  className="focus-ring-panel shrink-0 rounded px-2 py-1 text-label text-zinc-400 transition-colors hover:text-alarm disabled:opacity-40"
                >
                  {signingOut ? "Signing out…" : "Sign out"}
                </button>
              </div>
            )}
          </div>
        )}

      </nav>
    </RailCollapsedProvider>
  );
}

function RailToggle({ collapsed, onToggle }: { collapsed: boolean; onToggle: () => void }) {
  const label = collapsed ? "Expand sidebar" : "Collapse sidebar";
  return (
    <button
      onClick={onToggle}
      aria-label={label}
      aria-expanded={!collapsed}
      title={label}
      className="focus-ring-panel flex h-10 w-10 shrink-0 items-center justify-center rounded text-zinc-400 transition-colors hover:bg-zinc-900 hover:text-zinc-100"
    >
      <PanelToggleIcon collapsed={collapsed} size={18} />
    </button>
  );
}
