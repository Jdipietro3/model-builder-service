"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, Project } from "@/lib/api";

export default function Home() {
  const router = useRouter();
  const [projects, setProjects] = useState<Project[]>([]);
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

  return (
    <main className="flex flex-1 flex-col items-center px-6 py-16">
      <div className="w-full max-w-2xl">
        <div className="mb-10">
          <h1 className="text-display font-semibold tracking-tight">Model Builder</h1>
          <p className="mt-2 text-zinc-400">
            Describe your data and goal — get a trained model, an honest evaluation, and
            deployable code. No ML expertise required.
          </p>
        </div>

        {error && (
          <div className="mb-6 rounded-lg border border-red-900 bg-red-950/50 px-4 py-3 text-sm text-red-300">
            {error}
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
            className="focus-ring rounded-lg bg-emerald-600 px-5 py-2.5 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
          >
            {creating ? "Creating…" : "Create project"}
          </button>
        </div>

        {projects.length > 0 && (
          <div>
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
      </div>
    </main>
  );
}
