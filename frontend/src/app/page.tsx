"use client";

/**
 * The new-project screen: a composer waiting for a prompt or a CSV.
 *
 * There is no name field any more. The project is created by the first thing
 * you actually do, and named from it — a message becomes the title, a CSV
 * becomes its filename. That is the ChatGPT shape the rest of this layout
 * follows, and it works without a backend rename route (there isn't one).
 *
 * A message can't be streamed from here, since streaming needs
 * ProjectProvider's card handling — it is parked in pending-intent and claimed
 * by the provider on the other side of the navigation. An upload is a plain
 * REST call, so it happens here before we navigate.
 */

import { useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useProjects } from "@/lib/projects-context";
import { extractErrorDetail } from "@/lib/errors";
import { deriveProjectName, setPendingMessage } from "@/lib/pending-intent";
import Sidebar from "@/components/Sidebar";
import Composer from "@/components/Composer";
import MetisMark from "@/components/MetisMark";

export default function Home() {
  const router = useRouter();
  const { addProject, error: listError } = useProjects();
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function start(name: string, then?: (projectId: string) => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      const project = await api.createProject(name);
      addProject(project);
      if (then) await then(project.id);
      router.push(`/projects/${project.id}/model`);
    } catch (e) {
      setError(extractErrorDetail(e));
      setBusy(false);
    }
    // Deliberately not clearing busy on success: the route is changing, and
    // re-enabling the composer mid-navigation invites a double submit.
  }

  function onSend() {
    const text = input.trim();
    if (!text || busy) return;
    start(deriveProjectName(text, "message"), async (projectId) => {
      setPendingMessage(projectId, text);
    });
  }

  function onUpload(file: File) {
    if (busy) return;
    start(deriveProjectName(file.name, "filename"), async (projectId) => {
      await api.uploadDataset(projectId, file);
    });
  }

  return (
    <div className="flex h-full">
      <Sidebar />

      <main className="flex min-w-0 flex-1 flex-col items-center justify-center overflow-y-auto px-6 py-16">
        <div className="w-full max-w-2xl">
          <h1 className="flex items-center gap-2.5 text-display font-semibold tracking-tight">
            <MetisMark size={30} className="text-accent" />
            Metis
          </h1>
          <p className="measure mt-2 text-body text-zinc-400">
            Describe your data and goal — get a trained model, an honest evaluation, and
            deployable code. No ML expertise required.
          </p>

          {(error || listError) && (
            <div className="fade-in mt-6 flex items-start gap-2.5 rounded-lg bg-alarm-wash px-4 py-3 text-body text-alarm">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-alarm" />
              <span>{error ?? listError}</span>
            </div>
          )}

          <div className="mt-8">
            <Composer
              input={input}
              setInput={setInput}
              busy={busy}
              onSend={onSend}
              onUpload={onUpload}
              showUpload
              placeholder="Describe what you want to predict…"
            />
          </div>

          <p className="measure mt-3 text-label text-zinc-400">
            Attach a CSV, or just say what you are trying to do. The project takes its name
            from whichever comes first.
          </p>
        </div>
      </main>
    </div>
  );
}
