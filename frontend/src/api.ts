export type Health = { status: string; version: string; composition_revision: number | null };
export type Detection = { id: string; common_name: string; scientific_name?: string; confidence?: number; detected_at: string; source_type?: string };
export type Display = { revision?: number; mode?: string; image_url?: string; created_at?: string; species?: Array<{ common_name: string; count?: number }> };
export type RecentBird = { common_name: string; scientific_name?: string; count: number; confidence?: number; latest_at: string; image_url: string };

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { headers: { "Content-Type": "application/json", ...(init?.headers || {}) }, ...init });
  if (!response.ok) throw new Error((await response.text()) || `Request failed (${response.status})`);
  return response.status === 204 ? (undefined as T) : response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),
  settings: () => request<Record<string, unknown>>("/settings"),
  saveSettings: (body: Record<string, unknown>) => request<Record<string, unknown>>("/settings", { method: "PUT", body: JSON.stringify(body) }),
  display: () => request<Display>("/display/current.json"),
  birds: () => request<RecentBird[]>("/birds/recent"),
  refresh: () => request<Display>("/compositions/rebuild", { method: "POST" }),
  pushTv: () => request("/tv/push", { method: "POST" }),
  models: () => request<Array<{ id: string; name?: string; pricing?: unknown }>>("/openrouter/models"),
  occurrences: () => request<Array<{ common_name: string; scientific_name: string; score: number }>>("/art/occurrences"),
  generateArt: (body: { species: Array<{ common_name: string; scientific_name: string }>; model?: string; poses?: "one" | "both" }) => request<{ id: number }>("/art/generate", { method: "POST", body: JSON.stringify(body) }),
  packs: () => request<Array<{ id: string; illustrations: number; sketches: number }>>("/art/packs"),
  jobs: () => request<Array<{ id: number; kind: string; status: string; error?: string; updated_at: string }>>("/jobs"),
  logs: () => request<Array<{ id: number; level: string; message: string; created_at: string }>>("/logs?limit=100"),
};
