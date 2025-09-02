// pan-metrics-dashboard/src/api.ts

// We only respect VITE_API_BASE in dev if it's a FULL URL (http/https).
// In Docker prod (i.e. not Vite dev port 5173), we ALWAYS use "/api" so
// accidental bad envs like "/devices" can't break the app again.

const raw = (import.meta.env?.VITE_API_BASE ?? "").trim();
const isFullUrl = /^https?:\/\//i.test(raw);

// Are we on Vite dev server?
const isDev = typeof window !== "undefined" && window.location.port === "5173";

// Final base:
//  - Dev: prefer a full URL from env, else default to FastAPI on :8000
//  - Prod (Docker/nginx): always same-origin proxy at /api
export const API_BASE: string = isDev
  ? (isFullUrl ? raw : "http://localhost:8000")
  : "/api";

function join(base: string, path: string): string {
  const b = base.endsWith("/") ? base.slice(0, -1) : base;
  const p = path.startsWith("/") ? path : `/${path}`;
  return `${b}${p}`;
}

export async function fetchJSON<T>(path: string): Promise<T> {
  const url = join(API_BASE, path);
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text().catch(() => "");
    throw new Error(`GET ${url} -> ${res.status} ${res.statusText} ${text}`);
  }
  return res.json() as Promise<T>;
}
