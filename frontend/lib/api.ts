// Typed API client for all InsureIQ backend endpoints

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function call<T>(
  method: string,
  path: string,
  body?: unknown,
  token?: string,
): Promise<T> {
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const res = await fetch(`${BASE}${path}`, {
    method,
    headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail ?? detail; } catch { /* ignore */ }
    throw new ApiError(res.status, detail);
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

import type {
  TokenResponse, UserResponse, Workspace, Policy,
  UploadResponse, UploadListItem, ApiKey, ApiKeyCreated,
  GeneratedDocSummary, GeneratedDoc,
} from "./types";

export const api = {
  auth: {
    register: (d: { email: string; password: string; full_name?: string }) =>
      call<TokenResponse>("POST", "/auth/register", d),
    login: (d: { email: string; password: string }) =>
      call<TokenResponse>("POST", "/auth/login", d),
    me: (token: string) =>
      call<UserResponse>("GET", "/auth/me", undefined, token),
    updateMe: (d: Record<string, unknown>, token: string) =>
      call<UserResponse>("PATCH", "/auth/me", d, token),
    deleteMe: (token: string) =>
      call<void>("DELETE", "/auth/me", undefined, token),
    forgotPassword: (email: string) =>
      call("POST", "/auth/forgot-password", { email }),
    resetPassword: (d: { token: string; new_password: string }) =>
      call("POST", "/auth/reset-password", d),
  },

  workspaces: {
    list: (token: string) =>
      call<Workspace[]>("GET", "/workspaces", undefined, token),
    create: (d: { name: string; description?: string }, token: string) =>
      call<Workspace>("POST", "/workspaces", d, token),
    get: (id: string, token: string) =>
      call<Workspace>("GET", `/workspaces/${id}`, undefined, token),
    delete: (id: string, token: string) =>
      call<void>("DELETE", `/workspaces/${id}`, undefined, token),
  },

  policies: {
    list: (workspaceId: string, token: string) =>
      call<Policy[]>("GET", `/policies?workspace_id=${workspaceId}`, undefined, token),
    create: (d: { workspace_id: string; policy_data: Record<string, unknown> }, token: string) =>
      call<Policy>("POST", "/policies", d, token),
    get: (id: string, workspaceId: string, token: string) =>
      call<Policy>("GET", `/policies/${id}?workspace_id=${workspaceId}`, undefined, token),
    update: (id: string, workspaceId: string, d: Record<string, unknown>, token: string) =>
      call<Policy>("PATCH", `/policies/${id}?workspace_id=${workspaceId}`, d, token),
    delete: (id: string, workspaceId: string, token: string) =>
      call<void>("DELETE", `/policies/${id}?workspace_id=${workspaceId}`, undefined, token),
  },

  uploads: {
    list: (workspaceId: string, token: string) =>
      call<UploadListItem[]>("GET", `/uploads?workspace_id=${workspaceId}`, undefined, token),
    get: (id: string, workspaceId: string, token: string) =>
      call<UploadResponse>("GET", `/uploads/${id}?workspace_id=${workspaceId}`, undefined, token),
    delete: (id: string, workspaceId: string, token: string) =>
      call<void>("DELETE", `/uploads/${id}?workspace_id=${workspaceId}`, undefined, token),
  },

  search: {
    global: (query: string, limit = 10, token: string) =>
      call<{ query: string; results: unknown[] }>(
        "GET", `/search/global?query=${encodeURIComponent(query)}&limit=${limit}`, undefined, token,
      ),
    workspace: (workspaceId: string, query: string, limit = 10, token: string) =>
      call<{ query: string; workspace_id: string; results: unknown[] }>(
        "GET", `/search/workspace/${workspaceId}?query=${encodeURIComponent(query)}&limit=${limit}`, undefined, token,
      ),
    both: (query: string, workspaceId: string, limit = 10, token: string) =>
      call<{ global_results: unknown[]; workspace_results: unknown[] }>(
        "POST", "/search", { query, workspace_id: workspaceId, limit }, token,
      ),
  },

  chat: {
    history: (workspaceId: string, token: string, sessionId?: string) =>
      call<{ sessions?: unknown[]; messages?: unknown[]; session_id?: string }>(
        "GET",
        `/chat/history?workspace_id=${workspaceId}${sessionId ? `&session_id=${sessionId}` : ""}`,
        undefined,
        token,
      ),
    newSession: (workspaceId: string, token: string) =>
      call<{ session_id: string; workspace_id: string }>(
        "POST", `/chat/session?workspace_id=${workspaceId}`, undefined, token,
      ),
  },

  apiKeys: {
    list: (token: string) =>
      call<ApiKey[]>("GET", "/api-keys", undefined, token),
    create: (name: string, token: string) =>
      call<ApiKeyCreated>("POST", "/api-keys", { name }, token),
    revoke: (id: string, token: string) =>
      call<void>("DELETE", `/api-keys/${id}`, undefined, token),
  },

  generatedDocs: {
    list: (workspaceId: string, token: string, docType?: string) =>
      call<GeneratedDocSummary[]>(
        "GET",
        `/gen-docs?workspace_id=${workspaceId}${docType ? `&doc_type=${docType}` : ""}`,
        undefined,
        token,
      ),
    get: (id: string, workspaceId: string, token: string) =>
      call<GeneratedDoc>(
        "GET",
        `/gen-docs/${id}?workspace_id=${workspaceId}`,
        undefined,
        token,
      ),
    delete: (id: string, workspaceId: string, token: string) =>
      call<void>("DELETE", `/gen-docs/${id}?workspace_id=${workspaceId}`, undefined, token),
  },
};

export { ApiError };
