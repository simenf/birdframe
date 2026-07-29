export type Health = { status: string; version: string; composition_revision: number | null };
export type Detection = { id: string; common_name: string; scientific_name?: string; confidence?: number; detected_at: string; source_type?: string };
export type Display = { revision?: number; mode?: string; image_url?: string; created_at?: string; species?: Array<{ common_name: string; count?: number }> };

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
  detections: () => request<Detection[]>("/detections?hours=24"),
  refresh: () => request<Display>("/compositions/rebuild", { method: "POST" }),
  pushTv: () => request("/tv/push", { method: "POST" }),
  models: () => request<Array<{ id: string; name?: string; pricing?: unknown }>>("/openrouter/models"),
};
