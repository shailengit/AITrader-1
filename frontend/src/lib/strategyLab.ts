// Typed client for /api/strategy-lab/*

export interface ModelVariant {
  name: string;
  type: "cloud" | "local";
  size_bytes?: number;
}

export interface OllamaModel {
  id: string;
  variants: ModelVariant[];
}

export interface StrategySession {
  id: string;
  name: string;
  prompt: string;
  plan_text: string | null;
  code_text: string | null;
  model_id: string;
  tags: string[];
  created_at: string | null;
  updated_at: string | null;
}

export interface CreateSessionInput {
  name: string;
  prompt: string;
  model_id: string;
  tags?: string[];
}

export interface UpdateSessionInput {
  plan_text?: string;
  code_text?: string;
  tags?: string[];
  name?: string;
}

export interface ListSessionsParams {
  search?: string;
  tags?: string[];
  limit?: number;
  offset?: number;
}

export interface PlanResponse {
  plan_text: string;
}

export interface GenerateCodeResponse {
  code: string;
  validation_status?: string;
  validation_attempts?: number;
  validation_log?: string[];
}

export interface RefineCodeResponse {
  diff: string;
  summary: string;
}

export interface ApplyDiffResponse {
  code: string;
}

export interface ExperimentRow {
  id: string;
  session_id: string;
  batch_id: string;
  run_index: number;
  start_date: string | null;
  end_date: string | null;
  status: string;
  error_message: string | null;
  kpis: Record<string, any> | null;
  started_at: string | null;
  completed_at: string | null;
}

export interface BatchStats {
  n_total: number;
  n_completed: number;
  n_failed: number;
  mean_sharpe: number | null;
  best_sharpe: number | null;
  best_experiment_id: string | null;
  top_3: Array<{ id: string; run_index: number; start_date: string; sharpe: number; kpis: any }>;
  worst_3: Array<{ id: string; run_index: number; start_date: string; sharpe: number; kpis: any }>;
}

export interface SummarizeResponse {
  summary_id: string;
  summary_text: string;
  winner_run_id: string | null;
}

export interface RefineStrategyResponse {
  diff: string;
  summary: string;
  rationale: string;
}

export interface ChatMessage {
  id: string;
  role: string;
  content: string;
  model_id: string;
  critique_of?: string;
  created_at: string;
}

export interface ChatResponse {
  response: string;
  history: ChatMessage[];
}

export interface DeploymentInfo {
  deployment_id: string;
  class_name: string;
  class_file_path: string;
  is_active: boolean;
  deployed_at: string | null;
  rolled_back_at: string | null;
  experiment_id: string | null;
  session_id: string;
  verification?: Record<string, boolean>;
}

export interface DeploymentListItem {
  deployment_id: string;
  class_name: string;
  class_file_path: string;
  is_active: boolean;
  deployed_at: string | null;
  rolled_back_at: string | null;
  experiment_id: string | null;
  session_id: string;
}

const base = "/api/strategy-lab";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`GET ${url} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    // Try to parse the error body so the UI can show a useful message
    // instead of a bare "POST ... -> 502".
    let detail: unknown = null;
    try {
      detail = await res.json();
    } catch {
      detail = await res.text().catch(() => null);
    }
    const err = new Error(`POST ${url} -> ${res.status}`);
    (err as Error & { detail?: unknown; status?: number }).detail = detail;
    (err as Error & { detail?: unknown; status?: number }).status = res.status;
    throw err;
  }
  return res.json() as Promise<T>;
}

async function patchJson<T>(url: string, body: unknown): Promise<T> {
  const res = await fetch(url, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`PATCH ${url} -> ${res.status}`);
  return res.json() as Promise<T>;
}

async function deleteJson(url: string): Promise<void> {
  const res = await fetch(url, { method: "DELETE" });
  if (!res.ok && res.status !== 204) throw new Error(`DELETE ${url} -> ${res.status}`);
}

export const strategyLabApi = {
  listModels: () => getJson<OllamaModel[]>(`${base}/models`),

  listSessions: (params: ListSessionsParams = {}) => {
    const q = new URLSearchParams();
    if (params.search) q.set("search", params.search);
    if (params.tags && params.tags.length > 0) q.set("tags", params.tags.join(","));
    if (params.limit !== undefined) q.set("limit", String(params.limit));
    if (params.offset !== undefined) q.set("offset", String(params.offset));
    const qs = q.toString();
    return getJson<StrategySession[]>(`${base}/sessions${qs ? `?${qs}` : ""}`);
  },

  getSession: (id: string) => getJson<StrategySession>(`${base}/sessions/${id}`),

  createSession: (body: CreateSessionInput) => postJson<StrategySession>(`${base}/sessions`, body),

  updateSession: (id: string, body: UpdateSessionInput) =>
    patchJson<StrategySession>(`${base}/sessions/${id}`, body),

  deleteSession: (id: string) => deleteJson(`${base}/sessions/${id}`),

  generatePlan: (id: string, body: { model?: string } = {}) =>
    postJson<PlanResponse>(`${base}/sessions/${id}/plan`, body),

  generateCode: (id: string, body: { model?: string; plan_text?: string } = {}) =>
    postJson<GenerateCodeResponse>(`${base}/sessions/${id}/generate-code`, body),

  refineCode: (id: string, body: { model?: string; current_code?: string; instruction: string }) =>
    postJson<RefineCodeResponse>(`${base}/sessions/${id}/refine-code`, body),

  applyDiff: (id: string, body: { instruction: string; current_code?: string }) =>
    postJson<ApplyDiffResponse>(`${base}/sessions/${id}/apply-diff`, body),

  startExperiments: (id: string, body: { n_runs: number; end_date: string; start_date_min?: string; start_date_max?: string; model?: string }) =>
    postJson<{ batch_id: string }>(`${base}/sessions/${id}/experiments`, body),

  listExperiments: (id: string) => getJson<ExperimentRow[]>(`${base}/sessions/${id}/experiments`),

  listBatchExperiments: (id: string, batchId: string) =>
    getJson<ExperimentRow[]>(`${base}/sessions/${id}/batches/${batchId}/experiments`),

  getBatchStats: (id: string, batchId: string) =>
    getJson<BatchStats>(`${base}/sessions/${id}/batches/${batchId}/stats`),

  summarizeBatch: (id: string, batchId: string, body: { model?: string } = {}) =>
    postJson<SummarizeResponse>(`${base}/sessions/${id}/batches/${batchId}/summarize`, body),

  refineAfterBatch: (id: string, batchId: string, body: { model?: string } = {}) =>
    postJson<RefineStrategyResponse>(`${base}/sessions/${id}/batches/${batchId}/refine`, body),

  deploy: (id: string, body: { experiment_id: string; class_name?: string }) =>
    postJson<DeploymentInfo>(`${base}/sessions/${id}/deploy`, body),

  listDeployments: (params: { active_only?: boolean } = {}) => {
    const q = new URLSearchParams();
    if (params.active_only) q.set("active_only", "true");
    const qs = q.toString();
    return getJson<DeploymentListItem[]>(`${base}/deployments${qs ? `?${qs}` : ""}`);
  },

  rollbackDeployment: (deploymentId: string) =>
    postJson<{ rolled_back_deployment_id: string; new_active_class_name: string }>(
      `${base}/deployments/${deploymentId}/rollback`,
      {},
    ),

  chat: (id: string, body: { message: string; model: string; critique_of?: string }) =>
    postJson<ChatResponse>(`${base}/sessions/${id}/chat`, body),

  getChatHistory: (id: string) =>
    getJson<ChatMessage[]>(`${base}/sessions/${id}/chat`),
};
