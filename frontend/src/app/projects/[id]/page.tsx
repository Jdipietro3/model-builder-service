"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  Card,
  ChatMessage,
  Dataset,
  Deployment,
  Methodology,
  Plan,
  Prediction,
  ProjectDetail,
  Run,
} from "@/lib/api";

function extractErrorDetail(e: unknown): string {
  const msg = String(e instanceof Error ? e.message : e);
  const jsonStart = msg.indexOf("{");
  if (jsonStart >= 0) {
    try {
      const parsed = JSON.parse(msg.slice(jsonStart));
      if (parsed.detail) return String(parsed.detail);
    } catch {
      // fall through to raw message
    }
  }
  return msg;
}
import { MessageView, StreamingMessage } from "@/components/Chat";
import Workspace from "@/components/Workspace";

export interface RunState {
  status: string;
  progress: Run["progress"];
  results: Run["results"];
  error: string | null;
  live: boolean; // completed during this session
}

function Composer({
  input,
  setInput,
  busy,
  onSend,
  onUpload,
  showUpload,
}: {
  input: string;
  setInput: (v: string) => void;
  busy: boolean;
  onSend: () => void;
  onUpload: (f: File) => void;
  showUpload: boolean;
}) {
  return (
    <div className="flex items-end gap-2">
      {showUpload && (
        <label
          className={`flex h-10 w-10 shrink-0 cursor-pointer items-center justify-center rounded-lg border border-zinc-700 text-zinc-400 transition-colors hover:border-emerald-600 hover:text-emerald-500 ${busy ? "pointer-events-none opacity-40" : ""}`}
          title="Upload CSV"
        >
          <input
            type="file"
            accept=".csv"
            className="hidden"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) onUpload(f);
              e.target.value = "";
            }}
          />
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
            <path d="M12 16V4m0 0l-4 4m4-4l4 4" strokeLinecap="round" strokeLinejoin="round" />
            <path d="M4 16v3a1 1 0 001 1h14a1 1 0 001-1v-3" strokeLinecap="round" />
          </svg>
        </label>
      )}
      <textarea
        value={input}
        onChange={(e) => setInput(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            onSend();
          }
        }}
        rows={1}
        placeholder={busy ? "Working…" : "Ask about your data or model…"}
        className="max-h-40 min-h-10 flex-1 resize-y rounded-lg border border-zinc-800 bg-zinc-900 px-4 py-2.5 text-sm outline-none placeholder:text-zinc-500 focus:border-emerald-600"
      />
      <button
        onClick={onSend}
        disabled={busy || !input.trim()}
        className="h-10 rounded-lg bg-emerald-600 px-4 text-sm font-medium text-white transition-colors hover:bg-emerald-500 disabled:opacity-40"
      >
        Send
      </button>
    </div>
  );
}

export default function ProjectPage() {
  const { id } = useParams<{ id: string }>();
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [methodologies, setMethodologies] = useState<Methodology[]>([]);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [predictions, setPredictions] = useState<Prediction[]>([]);
  const [deployments, setDeployments] = useState<Deployment[]>([]);
  const [runStates, setRunStates] = useState<Record<string, RunState>>({});
  const [streamText, setStreamText] = useState<string | null>(null);
  const [streamCards, setStreamCards] = useState<Card[]>([]);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  // Tracks whether the component is still mounted, and mirrors `messages`' ids so
  // the interpretation poller (started from inside a callback, not an effect) can
  // dedupe against current state and be torn down cleanly on unmount.
  const mountedRef = useRef(true);
  const messageIdsRef = useRef<Set<string>>(new Set());
  const pollTimersRef = useRef<Set<ReturnType<typeof setInterval>>>(new Set());

  const workspaceMode = runs.length > 0;

  useEffect(() => {
    if (!id) return;
    Promise.all([api.getProject(id), api.listMethodologies(), api.listDeployments(id)])
      .then(([p, m, d]) => {
        setProject(p);
        setMethodologies(m);
        setMessages(p.messages.filter((msg) => !msg.hidden));
        setDatasets(p.datasets);
        setRuns(p.runs);
        setPredictions(p.predictions);
        setDeployments(d);
        const states: Record<string, RunState> = {};
        for (const r of p.runs) {
          states[r.id] = {
            status: r.status,
            progress: r.progress,
            results: r.results,
            error: r.error,
            live: false,
          };
        }
        setRunStates(states);
      })
      .catch((e) => setLoadError(String(e)));
  }, [id]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, streamText, streamCards]);

  useEffect(() => {
    messageIdsRef.current = new Set(messages.map((m) => m.id));
  }, [messages]);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      pollTimersRef.current.forEach((t) => clearInterval(t));
      pollTimersRef.current.clear();
    };
  }, []);

  // The training worker generates the results interpretation server-side once a
  // run completes (see backend/app/jobs.py::_interpret_run), so it lands even if
  // no client is around when training finishes. Poll briefly for the resulting
  // hidden-user + assistant message pair instead of triggering it ourselves.
  const pollForInterpretation = useCallback((projectId: string) => {
    const startedAt = Date.now();
    const POLL_INTERVAL_MS = 3000;
    const TIMEOUT_MS = 90000;
    const timer: ReturnType<typeof setInterval> = setInterval(async () => {
      if (!mountedRef.current || Date.now() - startedAt >= TIMEOUT_MS) {
        clearInterval(timer);
        pollTimersRef.current.delete(timer);
        return;
      }
      try {
        const p = await api.getProject(projectId);
        if (!mountedRef.current) return;
        setProject(p);
        const newOnes = p.messages.filter(
          (msg) => !msg.hidden && !messageIdsRef.current.has(msg.id),
        );
        if (newOnes.length > 0) {
          setMessages((prev) => [...prev, ...newOnes]);
          if (newOnes.some((msg) => msg.role === "assistant")) {
            clearInterval(timer);
            pollTimersRef.current.delete(timer);
          }
        }
      } catch {
        // Transient fetch error — keep polling until timeout.
      }
    }, POLL_INTERVAL_MS);
    pollTimersRef.current.add(timer);
  }, []);

  /** Open the SSE progress stream for a run and keep runStates in sync until it
   * reaches a terminal status (used by both approveRun and handleRetrain). */
  const watchRun = useCallback(
    (runId: string) => {
      const es = new EventSource(api.runEventsUrl(runId));
      es.onmessage = (ev) => {
        const data = JSON.parse(ev.data);
        setRunStates((prev) => ({
          ...prev,
          [runId]: {
            status: data.status,
            progress: data.progress,
            results: data.results ?? prev[runId]?.results ?? null,
            error: data.error ?? null,
            live: true,
          },
        }));
        if (data.status === "completed" || data.status === "failed") {
          es.close();
          if (data.status === "completed") {
            pollForInterpretation(id);
          }
        }
      };
      es.onerror = () => es.close();
    },
    [id, pollForInterpretation],
  );

  const send = useCallback(
    async (content: string, kind: "user" | "system_event" = "user") => {
      if (busy) return;
      setBusy(true);
      if (kind === "user") {
        setMessages((prev) => [
          ...prev,
          {
            id: `local-${Date.now()}`,
            role: "user",
            content,
            hidden: false,
            created_at: new Date().toISOString(),
          },
        ]);
      }
      setStreamText("");
      setStreamCards([]);
      let text = "";
      let cards: Card[] = [];
      await api.chatStream(id, content, kind, (e) => {
        if (e.type === "text_delta") {
          text += e.text;
          setStreamText(text);
        } else if (e.type === "card") {
          cards = [...cards, e.card];
          setStreamCards(cards);
          if (e.card.type === "plan") {
            // A proposed plan creates a pending run — surface it in the workspace.
            const now = new Date().toISOString();
            const run: Run = {
              id: e.card.run_id as string,
              project_id: id,
              dataset_id: e.card.dataset_id as string,
              status: "pending_approval",
              plan: e.card.plan as Plan,
              progress: null,
              results: null,
              error: null,
              created_at: now,
              updated_at: now,
            };
            setRuns((prev) => (prev.some((r) => r.id === run.id) ? prev : [...prev, run]));
            setRunStates((prev) => ({
              ...prev,
              [run.id]: {
                status: "pending_approval",
                progress: null,
                results: null,
                error: null,
                live: false,
              },
            }));
          } else if (e.card.type === "dataset_update") {
            // A dataset update pinned via chat (e.g. the user described a new
            // file) — mirror it into workspace state the same way the REST
            // update endpoint's response does in handleUpdateDataset.
            const c = e.card;
            const ds: Dataset = {
              id: c.dataset_id as string,
              filename: c.filename as string,
              profile: (c.profile ?? null) as Dataset["profile"],
              version: c.version as number,
              parent_dataset_id: c.parent_dataset_id as string,
              created_at: new Date().toISOString(),
            };
            setDatasets((prev) => (prev.some((d) => d.id === ds.id) ? prev : [...prev, ds]));
          } else if (e.card.type === "tournament") {
            // A proposed tournament creates one pending run per candidate plus a
            // waiting run for the auto-ensemble (if any) — surface all of them in
            // the workspace, same pattern as the plan branch above but N-wide.
            const c = e.card;
            const now = new Date().toISOString();
            const tournamentId = c.tournament_id as string;
            const datasetId = c.dataset_id as string;
            const candidates = c.candidates as { run_id: string; plan: Plan }[];
            const ensembleRun = c.ensemble_run as { run_id: string; plan: Plan } | null;
            const newRuns: Run[] = candidates.map((cand) => ({
              id: cand.run_id,
              project_id: id,
              dataset_id: datasetId,
              status: "pending_approval",
              plan: cand.plan,
              progress: null,
              results: null,
              error: null,
              tournament_id: tournamentId,
              tournament_role: "candidate",
              created_at: now,
              updated_at: now,
            }));
            if (ensembleRun) {
              newRuns.push({
                id: ensembleRun.run_id,
                project_id: id,
                dataset_id: datasetId,
                status: "waiting",
                plan: ensembleRun.plan,
                progress: null,
                results: null,
                error: null,
                tournament_id: tournamentId,
                tournament_role: "ensemble",
                created_at: now,
                updated_at: now,
              });
            }
            setRuns((prev) => {
              const existingIds = new Set(prev.map((r) => r.id));
              return [...prev, ...newRuns.filter((r) => !existingIds.has(r.id))];
            });
            setRunStates((prev) => {
              const next = { ...prev };
              for (const r of newRuns) {
                if (!next[r.id]) {
                  next[r.id] = {
                    status: r.status,
                    progress: null,
                    results: null,
                    error: null,
                    live: false,
                  };
                }
              }
              return next;
            });
          } else if (e.card.type === "retrain") {
            // The retrain tool already submitted training server-side by the
            // time this card streams down — synthesize the new run as queued
            // and start watching its progress, mirroring handleRetrain.
            const c = e.card;
            const now = new Date().toISOString();
            const run: Run = {
              id: c.run_id as string,
              project_id: id,
              dataset_id: c.dataset_id as string,
              status: "queued",
              plan: c.plan as Plan,
              progress: null,
              results: null,
              error: null,
              parent_run_id: c.parent_run_id as string,
              created_at: now,
              updated_at: now,
            };
            setRuns((prev) => (prev.some((r) => r.id === run.id) ? prev : [...prev, run]));
            setRunStates((prev) => ({
              ...prev,
              [run.id]: {
                status: "queued",
                progress: null,
                results: null,
                error: null,
                live: true,
              },
            }));
            watchRun(run.id);
          } else if (e.card.type === "recommendation") {
            setProject((prev) =>
              prev
                ? {
                    ...prev,
                    recommended_run_id: e.card.run_id as string,
                    recommendation_reason: e.card.reason as string,
                  }
                : prev,
            );
          }
        } else if (e.type === "error") {
          text += `${text ? "\n\n" : ""}⚠ ${e.message}`;
          setStreamText(text);
        }
      });
      if (text || cards.length) {
        setMessages((prev) => [
          ...prev,
          {
            id: `local-${Date.now()}`,
            role: "assistant",
            content: text,
            cards: cards.length ? cards : null,
            hidden: false,
            created_at: new Date().toISOString(),
          },
        ]);
      }
      setStreamText(null);
      setStreamCards([]);
      setBusy(false);
    },
    [busy, id, watchRun],
  );

  async function handleUpload(file: File) {
    setBusy(true);
    try {
      const ds = await api.uploadDataset(id, file);
      setDatasets((prev) => [...prev, ds]);
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}`,
          role: "assistant",
          content: "",
          cards: [
            { type: "profile", dataset_id: ds.id, filename: ds.filename, profile: ds.profile },
          ],
          hidden: false,
          created_at: new Date().toISOString(),
        },
      ]);
    } catch (e) {
      setMessages((prev) => [
        ...prev,
        {
          id: `local-${Date.now()}`,
          role: "assistant",
          content: `⚠ Upload failed: ${e}`,
          hidden: false,
          created_at: new Date().toISOString(),
        },
      ]);
    } finally {
      setBusy(false);
    }
  }

  const approveRun = useCallback(
    async (runId: string, overrides: Partial<Plan>) => {
      try {
        const run = await api.approveRun(runId, overrides);
        setRuns((prev) => prev.map((r) => (r.id === runId ? run : r)));
        setRunStates((prev) => ({
          ...prev,
          [runId]: {
            status: run.status,
            progress: run.progress,
            results: run.results,
            error: run.error,
            live: true,
          },
        }));
        watchRun(runId);
      } catch (e) {
        alert(`Could not start training: ${e}`);
      }
    },
    [watchRun],
  );

  const approveTournament = useCallback(
    async (tournamentId: string) => {
      try {
        const tournamentRuns = await api.approveTournament(tournamentId);
        setRuns((prev) => {
          const byId = new Map(prev.map((r) => [r.id, r]));
          for (const r of tournamentRuns) byId.set(r.id, r);
          // Preserve original order for existing runs; append any brand-new ones
          // (there shouldn't be any at this point, but stay defensive).
          const merged = prev.map((r) => byId.get(r.id) ?? r);
          for (const r of tournamentRuns) {
            if (!prev.some((p) => p.id === r.id)) merged.push(r);
          }
          return merged;
        });
        setRunStates((prev) => {
          const next = { ...prev };
          for (const run of tournamentRuns) {
            next[run.id] = {
              status: run.status,
              progress: run.progress,
              results: run.results,
              error: run.error,
              live: true,
            };
          }
          return next;
        });
        for (const run of tournamentRuns) watchRun(run.id);
      } catch (e) {
        alert(`Could not start tournament training: ${extractErrorDetail(e)}`);
      }
    },
    [watchRun],
  );

  const handlePredict = useCallback(
    async (runId: string, file: File) => {
      const p = await api.predict(runId, file);
      setPredictions((prev) => [...prev, p]);
    },
    [],
  );

  const handleDeploy = useCallback(
    async (runId: string, name?: string) => {
      try {
        const deployment = await api.createDeployment(id, runId, name);
        setDeployments((prev) =>
          prev.some((d) => d.id === deployment.id) ? prev : [...prev, deployment],
        );
      } catch (e) {
        alert(`Could not create deployment: ${extractErrorDetail(e)}`);
      }
    },
    [id],
  );

  const handlePromote = useCallback(async (deploymentId: string, runId: string) => {
    try {
      const updated = await api.promoteDeployment(deploymentId, runId);
      setDeployments((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
    } catch (e) {
      alert(`Could not promote deployment: ${extractErrorDetail(e)}`);
    }
  }, []);

  const handleSetDeploymentStatus = useCallback(
    async (deploymentId: string, status: "active" | "disabled") => {
      try {
        const updated = await api.setDeploymentStatus(deploymentId, status);
        setDeployments((prev) => prev.map((d) => (d.id === updated.id ? updated : d)));
      } catch (e) {
        alert(`Could not update deployment status: ${extractErrorDetail(e)}`);
      }
    },
    [],
  );

  const handleRetrain = useCallback(
    async (runId: string) => {
      try {
        const run = await api.retrainRun(runId);
        setRuns((prev) => (prev.some((r) => r.id === run.id) ? prev : [...prev, run]));
        setRunStates((prev) => ({
          ...prev,
          [run.id]: {
            status: run.status,
            progress: run.progress ?? null,
            results: null,
            error: null,
            live: true,
          },
        }));
        watchRun(run.id);
      } catch (e) {
        alert(`Could not retrain: ${extractErrorDetail(e)}`);
      }
    },
    [watchRun],
  );

  const handleUpdateDataset = useCallback(
    async (datasetId: string, file: File, mode: "replace" | "append") => {
      try {
        const res = await api.updateDataset(datasetId, file, mode);
        setDatasets((prev) => [...prev, res.dataset]);
        // The update endpoint pins a dataset_update card into chat history —
        // fetch once and merge any messages we don't have yet (same dedupe
        // approach as pollForInterpretation, just a single shot).
        try {
          const p = await api.getProject(id);
          if (!mountedRef.current) return;
          const newOnes = p.messages.filter(
            (msg) => !msg.hidden && !messageIdsRef.current.has(msg.id),
          );
          if (newOnes.length > 0) setMessages((prev) => [...prev, ...newOnes]);
        } catch {
          // Best effort — dataset state above is already correct either way.
        }
      } catch (e) {
        const detail = extractErrorDetail(e);
        setMessages((prev) => [
          ...prev,
          {
            id: `local-${Date.now()}`,
            role: "assistant",
            content: `⚠ Dataset update failed: ${detail}`,
            hidden: false,
            created_at: new Date().toISOString(),
          },
        ]);
        throw e;
      }
    },
    [id],
  );

  function doSend() {
    if (input.trim() && !busy) {
      send(input.trim());
      setInput("");
    }
  }

  if (loadError) {
    return (
      <main className="flex flex-1 items-center justify-center p-8">
        <div className="rounded-lg border border-red-900 bg-red-950/50 px-6 py-4 text-red-300">
          Failed to load project: {loadError}
        </div>
      </main>
    );
  }

  const chatCtx = {
    datasets,
    methodologies,
    runStates,
    onApprove: approveRun,
    onApproveTournament: approveTournament,
    compact: workspaceMode,
  };

  const messageList = (
    <>
      {messages.map((m) => (
        <MessageView key={m.id} message={m} {...chatCtx} />
      ))}
      {streamText !== null && (
        <StreamingMessage text={streamText} cards={streamCards} {...chatCtx} />
      )}
      <div ref={bottomRef} />
    </>
  );

  // ---------- Workspace mode: center workspace + right chat rail ----------
  if (workspaceMode) {
    return (
      <main className="flex h-screen flex-col">
        <header className="flex shrink-0 items-center gap-3 border-b border-zinc-800 px-6 py-3.5">
          <Link href="/" className="text-sm text-zinc-500 transition-colors hover:text-zinc-300">
            ← Projects
          </Link>
          <h1 className="text-lg font-semibold">{project?.name ?? "…"}</h1>
        </header>
        <div className="flex min-h-0 flex-1">
          <div className="min-w-0 flex-1 overflow-y-auto px-6 py-6">
            <Workspace
              datasets={datasets}
              runs={runs}
              runStates={runStates}
              predictions={predictions}
              deployments={deployments}
              methodologies={methodologies}
              onApprove={approveRun}
              onApproveTournament={approveTournament}
              onPredict={handlePredict}
              onUploadDataset={handleUpload}
              onRetrain={handleRetrain}
              onUpdateDataset={handleUpdateDataset}
              onDeploy={handleDeploy}
              onPromote={handlePromote}
              onSetStatus={handleSetDeploymentStatus}
              recommendedRunId={project?.recommended_run_id ?? null}
              recommendationReason={project?.recommendation_reason ?? null}
            />
          </div>
          <aside className="flex w-95 shrink-0 flex-col border-l border-zinc-800 bg-zinc-950">
            <div className="border-b border-zinc-800 px-4 py-2.5 text-xs font-medium uppercase tracking-wide text-zinc-500">
              Assistant
            </div>
            <div className="flex-1 space-y-4 overflow-y-auto px-4 py-4">{messageList}</div>
            <div className="border-t border-zinc-800 p-3">
              <Composer
                input={input}
                setInput={setInput}
                busy={busy}
                onSend={doSend}
                onUpload={handleUpload}
                showUpload={false}
              />
            </div>
          </aside>
        </div>
      </main>
    );
  }

  // ---------- Triage mode: full-width chat ----------
  return (
    <main className="mx-auto flex w-full max-w-4xl flex-1 flex-col px-4">
      <header className="sticky top-0 z-10 flex items-center gap-3 border-b border-zinc-800 bg-zinc-950/90 py-4 backdrop-blur">
        <Link href="/" className="text-sm text-zinc-500 transition-colors hover:text-zinc-300">
          ← Projects
        </Link>
        <h1 className="text-lg font-semibold">{project?.name ?? "…"}</h1>
      </header>

      <div className="flex-1 space-y-6 py-6">
        {messages.length === 0 && !streamText && (
          <div className="rounded-xl border border-dashed border-zinc-800 p-8 text-center text-zinc-500">
            <p className="font-medium text-zinc-400">Start by uploading a CSV</p>
            <p className="mt-1 text-sm">
              Then describe what you want to predict — e.g. “predict which customers will
              churn”. Model Builder will propose a training plan for your approval.
            </p>
          </div>
        )}
        {messageList}
      </div>

      <footer className="sticky bottom-0 border-t border-zinc-800 bg-zinc-950/90 py-4 backdrop-blur">
        <Composer
          input={input}
          setInput={setInput}
          busy={busy}
          onSend={doSend}
          onUpload={handleUpload}
          showUpload
        />
      </footer>
    </main>
  );
}
