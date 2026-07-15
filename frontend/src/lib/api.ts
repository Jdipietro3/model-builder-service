const API = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

// ---------- Types (mirror backend schemas) ----------

export interface Project {
  id: string;
  name: string;
  created_at: string;
}

export interface ColumnStats {
  mean: number;
  std: number;
  min: number;
  max: number;
}

export interface ColumnInfo {
  name: string;
  dtype: string;
  kind: string;
  n_unique: number;
  n_missing: number;
  pct_missing: number;
  sample_values: string[];
  stats?: ColumnStats;
}

export interface Profile {
  n_rows: number;
  n_cols: number;
  columns: ColumnInfo[];
  target_candidates: string[];
  warnings: string[];
}

export interface Plan {
  task_type: string;
  target_column: string;
  methodology_id: string;
  excluded_columns: string[];
  validation: { strategy: string; n_splits: number };
  primary_metric: string;
  reasoning: string;
}

export interface Card {
  type: "profile" | "plan" | "report";
  [key: string]: unknown;
}

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  cards?: Card[] | null;
  hidden: boolean;
  created_at: string;
}

export interface Dataset {
  id: string;
  filename: string;
  profile: Profile | null;
  created_at: string;
}

export interface RunProgress {
  stage: string;
  pct: number;
  message: string;
}

export interface HoldoutResults {
  metrics: Record<string, number>;
  baseline_metrics: Record<string, number>;
  baseline_description: string;
  confusion_matrix?: { labels: string[]; matrix: number[][] };
  residuals?: Record<string, number>;
}

export interface Results {
  methodology: { id: string; display_name: string };
  task_type: string;
  target_column: string;
  primary_metric: string;
  best_params: Record<string, unknown>;
  cv: { metric: string; mean: number; std: number; n_splits: number; n_candidates: number };
  holdout: HoldoutResults;
  feature_importances: { feature: string; importance: number; std: number }[];
  features_used: string[];
  features_dropped: { name: string; reason: string }[];
  caveats: string[];
  n_train: number;
  n_test: number;
  training_seconds: number;
}

export interface Run {
  id: string;
  project_id: string;
  dataset_id: string;
  status: string;
  plan: Plan;
  progress: RunProgress | null;
  results: Results | null;
  error: string | null;
  created_at: string;
  updated_at: string;
}

export interface ProjectDetail extends Project {
  messages: ChatMessage[];
  datasets: Dataset[];
  runs: Run[];
}

export interface Methodology {
  id: string;
  display_name: string;
  task_types: string[];
  when_to_use: string;
  metrics: Record<string, { default: string; supported: string[] }>;
}

export type ChatEvent =
  | { type: "text_delta"; text: string }
  | { type: "card"; card: Card }
  | { type: "done"; message_id: string }
  | { type: "error"; message: string };

// ---------- REST calls ----------

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`${res.status}: ${body}`);
  }
  return res.json();
}

export const api = {
  listProjects: () => fetch(`${API}/projects`).then((r) => json<Project[]>(r)),

  createProject: (name: string) =>
    fetch(`${API}/projects`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name }),
    }).then((r) => json<Project>(r)),

  getProject: (id: string) => fetch(`${API}/projects/${id}`).then((r) => json<ProjectDetail>(r)),

  uploadDataset: (projectId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API}/projects/${projectId}/datasets`, { method: "POST", body: form }).then(
      (r) => json<Dataset>(r),
    );
  },

  listMethodologies: () => fetch(`${API}/methodologies`).then((r) => json<Methodology[]>(r)),

  approveRun: (runId: string, planOverrides?: Partial<Plan>) =>
    fetch(`${API}/runs/${runId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_overrides: planOverrides ?? null }),
    }).then((r) => json<Run>(r)),

  artifactUrl: (runId: string) => `${API}/runs/${runId}/artifact`,

  runEventsUrl: (runId: string) => `${API}/runs/${runId}/events`,

  /** POST a chat message and stream back orchestrator events. */
  async chatStream(
    projectId: string,
    content: string,
    kind: "user" | "system_event",
    onEvent: (e: ChatEvent) => void,
  ): Promise<void> {
    const res = await fetch(`${API}/projects/${projectId}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ content, kind }),
    });
    if (!res.ok || !res.body) {
      onEvent({ type: "error", message: `Chat request failed (${res.status})` });
      return;
    }
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";
      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data: ")) continue;
        try {
          onEvent(JSON.parse(line.slice(6)) as ChatEvent);
        } catch {
          // ignore malformed frames
        }
      }
    }
  },
};
