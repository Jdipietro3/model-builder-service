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
  // Present on profiles generated after the enriched profiler.
  median?: number;
  p25?: number;
  p75?: number;
}

export interface TopValue {
  value: string;
  count: number;
  pct: number;
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
  top_values?: TopValue[];
}

export interface TargetAssociation {
  feature: string;
  score: number; // 0-1
  method: "pearson" | "cramers_v" | "correlation_ratio";
}

export interface Profile {
  // Optional fields only exist on profiles generated after the enriched profiler.
  data_shape?: string;
  n_rows: number;
  n_cols: number;
  sample_rows?: { columns: string[]; rows: string[][]; truncated_cols?: boolean };
  columns: ColumnInfo[];
  target_candidates: string[];
  time_column_candidates?: string[];
  warnings: string[];
  // Present on profiles generated after the leakage-aware profiler; absent on
  // datasets profiled before this change. Sorted score desc per target column.
  target_associations?: Record<string, TargetAssociation[]>;
}

export interface PlanWarning {
  category: "leakage" | "target_high_missingness" | "near_constant_feature";
  severity: "high" | "medium";
  message: string;
  columns: string[];
}

export interface Plan {
  task_type: string;
  target_column: string;
  methodology_id: string;
  excluded_columns: string[];
  validation: { strategy: string; n_splits: number };
  primary_metric: string;
  reasoning: string;
  // Present on forecasting plans (task_type === "forecasting", data_shape "timeseries").
  data_shape?: string;
  task_family?: string;
  time_column?: string | null;
  horizon?: number | null;
  // Ensemble-only: the tournament candidate run ids this ensemble blends/stacks.
  base_run_ids?: string[] | null;
  // Non-blocking pre-approval warnings (leakage, missingness, near-constant features).
  warnings?: PlanWarning[];
}

export interface Card {
  type: "profile" | "plan" | "report" | "dataset_update" | "retrain" | "tournament";
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
  version?: number;
  parent_dataset_id?: string | null;
  created_at: string;
}

export interface UpdateDiff {
  mode: string;
  rows_before: number;
  rows_after: number;
  rows_added: number;
  time_range_before?: [string, string] | null;
  time_range_after?: [string, string] | null;
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

// Forecasting series blocks (present only on task_family === "forecasting" results).
export interface HoldoutSeries {
  timestamps: string[];
  actual: number[];
  predicted: number[];
  lower: number[];
  upper: number[];
}

export interface ForecastSeries {
  timestamps: string[];
  yhat: number[];
  lower: number[];
  upper: number[];
}

export interface HistoryTail {
  timestamps: string[];
  actual: number[];
}

// Present only on ensemble runs' results (results.ensemble); the rest of the
// envelope fills normally so ReportCard renders unchanged.
export interface EnsembleInfo {
  type: "blend" | "stacking";
  base: {
    run_id: string;
    methodology_id: string;
    display_name: string;
    weight?: number;
    holdout_metrics: Record<string, number>;
  }[];
  weights?: Record<string, number>; // blend only
  meta_model?: { class: string; coefficients?: Record<string, unknown> }; // stacking only
}

export interface DiagnosticsSegment {
  column: string;
  metric: string;
  overall: number;
  segments: { value: string; n: number; metrics: Record<string, number> }[];
  worst: { value: string; n: number; score: number };
}

export interface DiagnosticsCalibration {
  metric: "brier";
  brier: number;
  bins: { p_pred: number; p_true: number; n: number }[];
}

export interface DiagnosticsSingleFeature {
  feature: string;
  solo_score: number;
  full_score: number;
  ratio: number;
}

export interface Diagnostics {
  segments: DiagnosticsSegment[];
  calibration: DiagnosticsCalibration | null;
  single_feature: DiagnosticsSingleFeature[];
}

export interface Results {
  methodology: { id: string; display_name: string };
  task_type: string;
  target_column: string;
  primary_metric: string;
  best_params: Record<string, unknown>;
  cv: { metric: string; mean: number; std: number; n_splits: number; n_candidates?: number };
  holdout: HoldoutResults;
  // Optional on forecasting results (they have no permutation importances).
  feature_importances?: { feature: string; importance: number; std: number }[];
  features_used?: string[];
  features_dropped?: { name: string; reason: string }[];
  caveats: string[];
  // Absent on runs trained before this change and on forecasting runs.
  diagnostics?: Diagnostics;
  n_train: number;
  n_test: number;
  training_seconds: number;
  // Forecasting-only fields (task_family === "forecasting", data_shape "timeseries").
  task_family?: string;
  data_shape?: string;
  time_column?: string;
  horizon?: number;
  freq?: string;
  holdout_series?: HoldoutSeries;
  forecast?: ForecastSeries;
  history_tail?: HistoryTail;
  // Ensemble-only.
  ensemble?: EnsembleInfo;
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
  parent_run_id?: string | null;
  tournament_id?: string | null;
  tournament_role?: "candidate" | "ensemble" | null;
  created_at: string;
  updated_at: string;
}

export interface PredictionSummary {
  n_rows: number;
  task_type: string;
  class_counts?: Record<string, number>;
  stats?: { mean: number; min: number; max: number };
  preview: { columns: string[]; rows: string[][] };
}

export interface Prediction {
  id: string;
  run_id: string;
  filename: string;
  n_rows: number;
  summary: PredictionSummary;
  created_at: string;
}

export interface ProjectDetail extends Project {
  messages: ChatMessage[];
  datasets: Dataset[];
  runs: Run[];
  predictions: Prediction[];
}

export interface Methodology {
  id: string;
  display_name: string;
  task_types: string[];
  when_to_use: string;
  metrics: Record<string, { default: string; supported: string[] }>;
  task_family: string;
}

export interface DeploymentContractFeature {
  name: string;
  dtype: string;
  example: unknown;
}

export interface DeploymentContract {
  feature_columns: DeploymentContractFeature[];
  target_column: string;
  task_type: string;
  example_record: Record<string, unknown>;
  endpoint: string;
}

export type Dist =
  | { kind: "class_counts"; proportions: Record<string, number> }
  | { kind: "stats"; mean: number; min: number; max: number };

export interface Deployment {
  id: string;
  project_id: string;
  run_id: string;
  name: string;
  status: "active" | "disabled";
  version: number;
  contract: DeploymentContract;
  training_distribution: Dist;
  created_at: string;
  updated_at: string;
}

export interface ServingStats {
  n_requests: number;
  n_rows: number;
  avg_latency_ms: number;
  served_distribution: Dist | null;
  training_distribution: Dist;
  drift_note: string;
}

export interface PredictResponse {
  predictions: unknown[];
  probabilities?: Record<string, number>[];
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

  updateDataset: (datasetId: string, file: File, mode: "replace" | "append") => {
    const form = new FormData();
    form.append("file", file);
    form.append("mode", mode);
    return fetch(`${API}/datasets/${datasetId}/update`, { method: "POST", body: form }).then((r) =>
      json<{ dataset: Dataset; diff: UpdateDiff }>(r),
    );
  },

  retrainRun: (runId: string) =>
    fetch(`${API}/runs/${runId}/retrain`, { method: "POST" }).then((r) => json<Run>(r)),

  listMethodologies: () => fetch(`${API}/methodologies`).then((r) => json<Methodology[]>(r)),

  approveRun: (runId: string, planOverrides?: Partial<Plan>) =>
    fetch(`${API}/runs/${runId}/approve`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ plan_overrides: planOverrides ?? null }),
    }).then((r) => json<Run>(r)),

  approveTournament: (tournamentId: string) =>
    fetch(`${API}/tournaments/${tournamentId}/approve`, { method: "POST" }).then((r) =>
      json<Run[]>(r),
    ),

  artifactUrl: (runId: string) => `${API}/runs/${runId}/artifact`,

  predict: (runId: string, file: File) => {
    const form = new FormData();
    form.append("file", file);
    return fetch(`${API}/runs/${runId}/predictions`, { method: "POST", body: form }).then(
      (r) => json<Prediction>(r),
    );
  },

  predictionDownloadUrl: (predictionId: string) => `${API}/predictions/${predictionId}/download`,

  runEventsUrl: (runId: string) => `${API}/runs/${runId}/events`,

  createDeployment: (projectId: string, runId: string, name?: string) =>
    fetch(`${API}/projects/${projectId}/deployments`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId, name: name ?? null }),
    }).then((r) => json<Deployment>(r)),

  listDeployments: (projectId: string) =>
    fetch(`${API}/projects/${projectId}/deployments`).then((r) => json<Deployment[]>(r)),

  getDeployment: (id: string) => fetch(`${API}/deployments/${id}`).then((r) => json<Deployment>(r)),

  predictDeployment: (id: string, records: Record<string, unknown>[]) =>
    fetch(`${API}/deployments/${id}/predict`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ records }),
    }).then((r) => json<PredictResponse>(r)),

  getDeploymentStats: (id: string) =>
    fetch(`${API}/deployments/${id}/stats`).then((r) => json<ServingStats>(r)),

  promoteDeployment: (id: string, runId: string) =>
    fetch(`${API}/deployments/${id}/promote`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ run_id: runId }),
    }).then((r) => json<Deployment>(r)),

  setDeploymentStatus: (id: string, status: "active" | "disabled") =>
    fetch(`${API}/deployments/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status }),
    }).then((r) => json<Deployment>(r)),

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
