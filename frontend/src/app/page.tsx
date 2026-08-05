"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Project } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    api
      .listProjects()
      .then(setProjects)
      .catch(() => setError("Backend not reachable at localhost:8000 — is it running?"));
  }, []);

  async function create() {
    if (!name.trim() || creating) return;
    setCreating(true);
    try {
      const project = await api.createProject(name.trim());
      router.push(`/projects/${project.id}`);
    } catch (e) {
      setError(String(e));
      setCreating(false);
    }
  }

  const loading = projects === null && !error;

  return (
    <main className="flex flex-1 flex-col items-center px-6 py-16">
      <div className="w-full max-w-2xl">
        <div className="mb-10">
          <div className="flex items-center gap-3">
            <h1 className="text-display font-semibold tracking-tight">Model Builder</h1>
            {loading && (
              <span className="flex items-center gap-1.5 text-xs text-zinc-400">
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-sky-400" />
                Connecting
              </span>
            )}
          </div>
          <p className="mt-2 text-zinc-400">
            Describe your data and goal — get a trained model, an honest evaluation, and
            deployable code. No ML expertise required.
          </p>
        </div>

        {error && (
          <div className="fade-in mb-6 flex items-start gap-2.5 rounded-lg border border-red-900 bg-red-950/50 px-4 py-3 text-sm text-red-300">
            <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-red-500" />
            <span>{error}</span>
          </div>
        )}

        <div className="mb-10 flex gap-2">
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && create()}
            placeholder="New project name, e.g. 'Churn prediction'"
            className="focus-ring flex-1 rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm outline-none placeholder:text-zinc-400 focus:border-emerald-600"
          />
          <button
            onClick={create}
            disabled={!name.trim() || creating}
            className="focus-ring flex items-center gap-2 rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
          >
            {creating && (
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-white/40 border-t-white" />
            )}
            {creating ? "Creating…" : "Create project"}
          </button>
        </div>

        {loading && (
          <div className="space-y-2" aria-hidden="true">
            <div className="h-11 animate-pulse rounded-lg bg-zinc-900" />
            <div className="h-11 animate-pulse rounded-lg bg-zinc-900/60" />
          </div>
        )}

        {projects && projects.length > 0 && (
          <div className="fade-in">
            <h2 className="mb-3 text-headline font-semibold text-zinc-100">Projects</h2>
            <ul className="divide-y divide-zinc-800 overflow-hidden rounded-lg border border-zinc-800">
              {projects.map((p) => (
                <li key={p.id}>
                  <button
                    onClick={() => router.push(`/projects/${p.id}`)}
                    className="focus-ring-panel flex w-full items-center justify-between bg-zinc-900/60 px-4 py-3 text-left transition-colors hover:bg-zinc-900"
                  >
                    <span className="font-medium">{p.name}</span>
                    <span className="text-xs text-zinc-400">
                      {new Date(p.created_at).toLocaleDateString()}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}

        {projects && projects.length === 0 && (
          <div className="fade-in rounded-lg border border-dashed border-zinc-800 px-6 py-8 text-center">
            <p className="font-medium text-zinc-300">No projects yet</p>
            <p className="mx-auto mt-1.5 max-w-sm text-sm text-zinc-400">
              Create one above, then upload a CSV and describe what you want to predict —
              e.g. &ldquo;predict which customers will churn&rdquo;.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
