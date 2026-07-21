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
  if (!res.ok) throw new Error(`POST ${url} -> ${res.status}`);
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
};
