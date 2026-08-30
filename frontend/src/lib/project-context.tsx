"use client";

/**
 * All project state, hoisted above the tab routes.
 *
 * WHY THIS EXISTS: every tab under /projects/[id] is its own route segment, so
 * each one mounts and unmounts as the user navigates. The live machinery here —
 * one EventSource per training run (`watchRun`) and the post-training
 * interpretation poller — must outlive that. Held inside a tab, switching from
 * Model to Metrics mid-training would tear down the SSE stream and the run would
 * appear to stall. This provider is mounted by projects/[id]/layout.tsx, which
 * Next.js keeps alive across sibling route changes, so the streams survive.
 *
 * This is a near-verbatim lift of what ProjectPage used to hold. The one genuine
 * addition is `selectedRunId`: run selection used to be local state inside
 * Workspace, and now the sidebar's model dropdown and all five tabs read the
 * same value.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
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
import { extractErrorDetail } from "@/lib/errors";
import { takePendingMessage } from "@/lib/pending-intent";

export interface RunState {
  status: string;
  progress: Run["progress"];
  results: Run["results"];
  error: string | null;
  live: boolean; // completed during this session
}

export interface ProjectContextValue {
  projectId: string;
  project: ProjectDetail | null;
  methodologies: Methodology[];
  messages: ChatMessage[];
  datasets: Dataset[];
  runs: Run[];
  predictions: Prediction[];
  deployments: Deployment[];
  runStates: Record<string, RunState>;
  streamText: string | null;
  streamCards: Card[];
  busy: boolean;
  loadError: string | null;
  /** True until the first project fetch resolves. Tabs must distinguish this
   *  from "empty": a deep link to /metrics would otherwise flash "no results
   *  yet" at a user whose run finished days ago. */
  loading: boolean;

  /** Newest-first runs, and the currently selected one. Shared by the sidebar
   *  model dropdown and every tab so they can never disagree. */
  orderedRuns: Run[];
  selectedRun: Run | undefined;
  selectedRunId: string | null;
  setSelectedRunId: (id: string) => void;

  input: string;
  setInput: (v: string) => void;

  send: (content: string, kind?: "user" | "system_event") => Promise<void>;
  handleUpload: (file: File) => Promise<void>;
  approveRun: (runId: string, overrides: Partial<Plan>) => Promise<void>;
  approveTournament: (tournamentId: string) => Promise<void>;
  handlePredict: (runId: string, file: File) => Promise<void>;
  handleDeploy: (runId: string, name?: string) => Promise<void>;
  handlePromote: (deploymentId: string, runId: string) => Promise<void>;
  handleSetDeploymentStatus: (
    deploymentId: string,
    status: "active" | "disabled",
  ) => Promise<void>;
  handleRetrain: (runId: string) => Promise<void>;
  handleUpdateDataset: (
    datasetId: string,
    file: File,
    mode: "replace" | "append",
  ) => Promise<void>;
}

const ProjectContext = createContext<ProjectContextValue | null>(null);

export function useProject(): ProjectContextValue {
  const ctx = useContext(ProjectContext);
  if (!ctx) throw new Error("useProject must be used inside a ProjectProvider");
  return ctx;
}

export function ProjectProvider({
  projectId: id,
  children,
}: {
  projectId: string;
  children: React.ReactNode;
}) {
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
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);

  // Tracks whether the provider is still mounted, and mirrors `messages`' ids so
  // the interpretation poller (started from inside a callback, not an effect) can
  // dedupe against current state and be torn down cleanly on unmount.
  const mountedRef = useRef(true);
  const messageIdsRef = useRef<Set<string>>(new Set());
  const pollTimersRef = useRef<Set<ReturnType<typeof setInterval>>>(new Set());

  const orderedRuns = useMemo(() => runs.slice().reverse(), [runs]); // newest first
  const selectedRun =
    orderedRuns.find((r) => r.id === selectedRunId) ?? orderedRuns[0];

  // Default the selection to the newest run once runs exist, and re-point it if
  // the selected run disappears. Mirrors Workspace's old local effect.
  useEffect(() => {
    if (orderedRuns.length === 0) return;
    if (!selectedRunId || !orderedRuns.some((r) => r.id === selectedRunId)) {
      setSelectedRunId(orderedRuns[0].id);
    }
  }, [orderedRuns, selectedRunId]);

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
    messageIdsRef.current = new Set(messages.map((m) => m.id));
  }, [messages]);

  useEffect(() => {
    mountedRef.current = true;
    const timers = pollTimersRef.current;
    return () => {
      mountedRef.current = false;
      timers.forEach((t) => clearInterval(t));
      timers.clear();
    };
  }, []);

  // The training worker generates the results interpretation server-side once a
  // run completes (see backend/app/jobs.py::_interpret_run), so it lands even if
  // no client is around when training finishes. Poll briefly for the resulting
  // hidden-user + assistant message pair instead of triggering it ourselves.
  const pollForInterpretation = useCallback((pid: string) => {
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
        const p = await api.getProject(pid);
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

  // Claim the message typed on `/` before this project existed. Guarded by a ref
  // as well as takePendingMessage's own one-shot semantics, because `send`
  // changes identity every time `busy` flips and would otherwise re-fire.
  const claimedPendingRef = useRef(false);
  useEffect(() => {
    if (claimedPendingRef.current) return;
    const pendingMessage = takePendingMessage(id);
    if (!pendingMessage) return;
    claimedPendingRef.current = true;
    send(pendingMessage);
  }, [id, send]);

  const handleUpload = useCallback(
    async (file: File) => {
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
    },
    [id],
  );

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

  const handlePredict = useCallback(async (runId: string, file: File) => {
    const p = await api.predict(runId, file);
    setPredictions((prev) => [...prev, p]);
  }, []);

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

  const value: ProjectContextValue = {
    projectId: id,
    project,
    methodologies,
    messages,
    datasets,
    runs,
    predictions,
    deployments,
    runStates,
    streamText,
    streamCards,
    busy,
    loadError,
    loading: project === null && !loadError,
    orderedRuns,
    selectedRun,
    selectedRunId,
    setSelectedRunId,
    input,
    setInput,
    send,
    handleUpload,
    approveRun,
    approveTournament,
    handlePredict,
    handleDeploy,
    handlePromote,
    handleSetDeploymentStatus,
    handleRetrain,
    handleUpdateDataset,
  };

  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>;
}
