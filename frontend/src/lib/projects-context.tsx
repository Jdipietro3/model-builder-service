"use client";

/**
 * The project LIST, held at the root so the sidebar never re-fetches it.
 *
 * Deliberately separate from ProjectProvider, which owns one project's full
 * state. This holds only what the rail renders (id, name, created_at) and lives
 * above every route, so moving between `/` and a project — or between two
 * projects — never flashes an empty rail.
 */

import { createContext, useCallback, useContext, useEffect, useState } from "react";
import { api, Project } from "@/lib/api";

interface ProjectsContextValue {
  projects: Project[] | null; // null while the first fetch is in flight
  error: string | null;
  refresh: () => Promise<void>;
  /** Insert a just-created project without waiting for a round trip. */
  addProject: (p: Project) => void;
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

  const refresh = useCallback(async () => {
    try {
      const list = await api.listProjects();
      setProjects(list);
      setError(null);
    } catch {
      setError("Backend not reachable at localhost:8000 — is it running?");
    }
  }, []);

  const addProject = useCallback((p: Project) => {
    setProjects((prev) => (prev?.some((x) => x.id === p.id) ? prev : [p, ...(prev ?? [])]));
  }, []);

  useEffect(() => {
    refresh();
  }, [refresh]);

  return (
    <ProjectsContext.Provider value={{ projects, error, refresh, addProject }}>
      {children}
    </ProjectsContext.Provider>
  );
}
