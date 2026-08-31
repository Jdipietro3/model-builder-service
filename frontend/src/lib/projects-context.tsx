"use client";

/**
 * The project LIST, held at the root so the sidebar never re-fetches it.
 *
 * Deliberately separate from ProjectProvider, which owns one project's full
 * state. This holds only what the rail renders (id, name, created_at) and lives
 * above every route, so moving between `/` and a project — or between two
 * projects — never flashes an empty rail.
 *
 * Also holds the signed-in user. That's a different concern from the project
 * list, but it's the same "app-level state above every route" shape, and the
 * signed-in email lives in this same rail (Sidebar's footer) — a second
 * provider just to fetch one /auth/me would duplicate the mount-and-fetch
 * wiring below for no benefit.
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { api, AuthUser, Project } from "@/lib/api";

/** Routes that render before anyone is signed in. Fetching here is guaranteed
 *  to 401, so the provider stays idle rather than firing two doomed requests
 *  and logging two console errors on every visit to the login page. */
const PRE_AUTH_ROUTES = new Set(["/login", "/signup"]);

interface ProjectsContextValue {
  projects: Project[] | null; // null while the first fetch is in flight
  error: string | null;
  refresh: () => Promise<void>;
  /** Insert a just-created project without waiting for a round trip. */
  addProject: (p: Project) => void;

  /** null covers both "still loading" and "signed out" — check userLoading
   *  to tell them apart so a footer never flashes signed-out before the
   *  first /auth/me resolves. */
  user: AuthUser | null;
  userLoading: boolean;
}

const ProjectsContext = createContext<ProjectsContextValue | null>(null);

export function useProjects(): ProjectsContextValue {
  const ctx = useContext(ProjectsContext);
  if (!ctx) throw new Error("useProjects must be used inside a ProjectsProvider");
  return ctx;
}

export function ProjectsProvider({ children }: { children: React.ReactNode }) {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [userLoading, setUserLoading] = useState(true);

  // One entry point refreshes both the project list and the signed-in user,
  // so login/signup can call it once after a successful auth response and
  // have the rail (list + footer) catch up without a full page reload.
  const refresh = useCallback(async () => {
    try {
      const list = await api.listProjects();
      setProjects(list);
      setError(null);
    } catch (e) {
      // Distinguish "signed out" from "server is down". apiFetch throws a
      // `401:`-prefixed error and has already redirected to /login; reporting
      // that as "backend not reachable" would be a plain lie, and it is the
      // message the user reads while the redirect is still in flight.
      const unauthenticated = String(e instanceof Error ? e.message : e).startsWith("401:");
      setError(unauthenticated ? null : "Backend not reachable at localhost:8000 — is it running?");
    }
    try {
      setUser(await api.me());
    } catch {
      setUser(null);
    } finally {
      setUserLoading(false);
    }
  }, []);

  const addProject = useCallback((p: Project) => {
    setProjects((prev) => (prev?.some((x) => x.id === p.id) ? prev : [p, ...(prev ?? [])]));
  }, []);

  const pathname = usePathname();
  const preAuth = PRE_AUTH_ROUTES.has(pathname);

  useEffect(() => {
    if (preAuth) {
      // Nothing to load, and nothing is waiting on it: the auth pages render no
      // rail. Resolve the loading flag so a later sign-in is not stuck behind it.
      setUserLoading(false);
      return;
    }
    refresh();
  }, [refresh, preAuth]);

  return (
    <ProjectsContext.Provider
      value={{ projects, error, refresh, addProject, user, userLoading }}
    >
      {children}
    </ProjectsContext.Provider>
  );
}
