/** Thin typed wrapper over the backend API. */

import type {
  Airport,
  Coverage,
  Disclaimer,
  Health,
  SearchParams,
  SearchResult,
} from "../types";

// Same-origin by default: the Vite dev proxy and a same-origin production
// deploy both want a bare "/api".
export const API_BASE = import.meta.env.VITE_API_BASE || "/api";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

/** Flattens FastAPI/Pydantic error shapes into one readable sentence. */
function extractDetail(payload: unknown, fallback: string): string {
  if (typeof payload !== "object" || payload === null) return fallback;
  const detail = (payload as { detail?: unknown }).detail;

  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item !== "object" || item === null) return null;
        const { msg, loc } = item as { msg?: string; loc?: unknown[] };
        if (!msg) return null;
        const field = Array.isArray(loc) ? loc.at(-1) : undefined;
        return field ? `${String(field)}: ${msg}` : msg;
      })
      .filter(Boolean);
    if (messages.length) return messages.join("; ");
  }
  return fallback;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });

  if (!response.ok) {
    const payload = await response.json().catch(() => null);
    throw new ApiError(
      extractDetail(payload, `Request failed with status ${response.status}`),
      response.status,
    );
  }
  return response.json() as Promise<T>;
}

export const api = {
  health: () => request<Health>("/health"),

  coverage: () => request<Coverage>("/coverage"),

  disclaimer: (lang: string) =>
    request<Disclaimer>(`/disclaimer?lang=${encodeURIComponent(lang)}`),

  airports: (query: string, limit = 8) =>
    request<Airport[]>(`/airports?q=${encodeURIComponent(query)}&limit=${limit}`),

  /** Queues a search and returns its id; progress arrives over SSE. */
  startSearch: (params: SearchParams) =>
    request<{ search_id: string; stream_url: string; result_url: string }>("/search", {
      method: "POST",
      body: JSON.stringify(params),
    }),

  getSearch: (searchId: string) => request<SearchResult>(`/search/${searchId}`),

  acknowledge: (searchId: string, clientToken: string, version: string) =>
    request<{ acknowledged: boolean; version: string; acknowledged_at: string }>(
      `/search/${searchId || "none"}/acknowledge`,
      {
        method: "POST",
        body: JSON.stringify({ client_token: clientToken, version }),
      },
    ),

  eventStreamUrl: (searchId: string) => `${API_BASE}/search/${searchId}/events`,
};
