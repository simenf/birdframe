export type Health = { status: string; version: string; composition_revision: number | null; needs_setup?: boolean; needs_admin?: boolean };
export type Detection = { id: string; common_name: string; scientific_name?: string; confidence?: number; detected_at: string; source_type?: string };
export type Display = { revision?: number; mode?: string; image_url?: string; created_at?: string; species?: Array<{ common_name: string; count?: number }> };
export type RecentBird = { common_name: string; scientific_name?: string; count: number; confidence?: number; latest_at: string; image_url: string; has_artwork?: boolean };
export type LogEntry = { id: number; level: string; message: string; created_at: string };
export type LogPage = { items: LogEntry[]; total: number; limit: number; offset: number };
export type SourceTestResult = { available: boolean; detail?: string | null };
export type User = { id: number; username: string; is_admin: boolean; created_at: string };
export type AuthSession = { username: string; is_admin: boolean; api_key: string };
export type ApiKey = { id: number; name: string; prefix: string; created_at: string; last_used_at?: string | null };
export type ApiKeyCreated = ApiKey & { key: string };

const API_KEY_STORAGE = "birdframe_api_key";

let apiKey = "";
try { apiKey = localStorage.getItem(API_KEY_STORAGE) || ""; } catch { apiKey = ""; }

export function getApiKey(): string { return apiKey; }
export function setApiKey(key: string): void {
  apiKey = key;
  try {
    if (key) localStorage.setItem(API_KEY_STORAGE, key);
    else localStorage.removeItem(API_KEY_STORAGE);
  } catch { /* private mode or unavailable storage */ }
}

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) { super(message); this.status = status; }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { ...(init?.headers as Record<string, string> | undefined) };
  if (!(init?.body instanceof FormData)) headers["Content-Type"] = "application/json";
  if (apiKey) headers["Authorization"] = `Bearer ${apiKey}`;
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), 30000);
  try {
    const response = await fetch(`/api/v1${path}`, { ...init, headers, signal: controller.signal });
    if (!response.ok) {
      let detail = `Request failed (${response.status})`;
      try { detail = (await response.json()).detail || detail; } catch { /* non-JSON error body */ }
      throw new ApiError(response.status, detail);
    }
    return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
  } catch (err) {
    if (err instanceof Error && err.name === "AbortError") {
      throw new ApiError(0, "Request timed out — is the BirdFrame service reachable?");
    }
    throw err;
  } finally {
    window.clearTimeout(timer);
  }
}

export const api = {
  health: () => request<Health>("/health"),
  bootstrap: (username: string, password: string) => request<AuthSession>("/auth/bootstrap", { method: "POST", body: JSON.stringify({ username, password }) }),
  login: (username: string, password: string) => request<AuthSession>("/auth/login", { method: "POST", body: JSON.stringify({ username, password }) }),
  logout: () => request("/auth/logout", { method: "POST" }),
  me: () => request<{ username: string; is_admin: boolean }>("/auth/me"),
  listApiKeys: () => request<ApiKey[]>("/auth/api-keys"),
  createApiKey: (name: string) => request<ApiKeyCreated>("/auth/api-keys", { method: "POST", body: JSON.stringify({ name }) }),
  revokeApiKey: (keyId: number) => request(`/auth/api-keys/${keyId}`, { method: "DELETE" }),
  listUsers: () => request<User[]>("/users"),
  createUser: (body: { username: string; password: string; is_admin?: boolean }) => request<User>("/users", { method: "POST", body: JSON.stringify(body) }),
  settings: () => request<Record<string, unknown>>("/settings"),
  saveSettings: (body: Record<string, unknown>) => request<Record<string, unknown>>("/settings", { method: "PUT", body: JSON.stringify(body) }),
  testSource: (body: { source: "birdnet_go"; url?: string }) => request<SourceTestResult>("/sources/test", { method: "POST", body: JSON.stringify(body) }),
  display: () => request<Display>("/display/current.json"),
  birds: () => request<RecentBird[]>("/birds/recent"),
  refresh: () => request<Display>("/compositions/rebuild", { method: "POST" }),
  pushTv: () => request<{ id: number }>("/tv/push", { method: "POST" }),
  models: () => request<Array<{ id: string; name?: string; pricing?: unknown }>>("/openrouter/models"),
  occurrences: () => request<Array<{ common_name: string; scientific_name: string; score: number; has_artwork?: boolean }>>("/art/occurrences"),
  generateArt: (body: { species: Array<{ common_name: string; scientific_name: string }>; model?: string; poses?: "one" | "both" }) => request<{ id: number }>("/art/generate", { method: "POST", body: JSON.stringify(body) }),
  packs: () => request<Array<{ id: string; illustrations: number; sketches: number }>>("/art/packs"),
  packageCatalog: () => request<Array<{ id: string; version?: string; download_url: string; sha256: string }>>("/art/packages/catalog"),
  uploadPackage: (file: File) => request<{ id: number }>("/art/packages/upload", { method: "POST", headers: { "Content-Type": "application/zip", "X-BirdFrame-Filename": file.name }, body: file }),
  installPackageUrl: (url: string, package_id?: string) => request<{ id: number }>("/art/packages/install-url", { method: "POST", body: JSON.stringify({ url, package_id: package_id || "" }) }),
  jobs: () => request<Array<{ id: number; kind: string; status: string; error?: string; updated_at: string; result?: { phase?: string; progress?: number } }>>("/jobs"),
  logs: (offset = 0, limit = 25) => request<LogPage>(`/logs?limit=${limit}&offset=${offset}`),
};
