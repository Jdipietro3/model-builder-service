"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import {
  api,
  Card,
  ChatMessage,
  Dataset,
  Methodology,
  Plan,
  Prediction,
  ProjectDetail,
  Run,
} from "@/lib/api";
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
  const [runStates, setRunStates] = useState<Record<string, RunState>>({});
  const [streamText, setStreamText] = useState<string | null>(null);
  const [streamCards, setStreamCards] = useState<Card[]>([]);
  const [busy, setBusy] = useState(false);
  const [input, setInput] = useState("");
  const [loadError, setLoadError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  const workspaceMode = runs.length > 0;

  useEffect(() => {
    if (!id) return;
    Promise.all([api.getProject(id), api.listMethodologies()])
      .then(([p, m]) => {
        setProject(p);
        setMethodologies(m);
        setMessages(p.messages.filter((msg) => !msg.hidden));
        setDatasets(p.datasets);
        setRuns(p.runs);
        setPredictions(p.predictions);
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
    [busy, id],
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
              send(
                `[system notification] Training run ${runId} has completed. Call get_results and give the user a plain-language interpretation: headline metric vs the naive baseline, what drives predictions, and any caveats.`,
                "system_event",
              );
            }
          }
        };
        es.onerror = () => es.close();
      } catch (e) {
        alert(`Could not start training: ${e}`);
      }
    },
    [send],
  );

  const handlePredict = useCallback(
    async (runId: string, file: File) => {
      const p = await api.predict(runId, file);
      setPredictions((prev) => [...prev, p]);
    },
    [],
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
              methodologies={methodologies}
              onApprove={approveRun}
              onPredict={handlePredict}
              onUploadDataset={handleUpload}
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
