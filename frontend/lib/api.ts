/**
 * LeadForge API client.
 *
 * On the browser we route through Next.js' `/api/backend/*` rewrite (see next.config.mjs),
 * which proxies to FastAPI under /api/v1. On the server we hit the API directly via
 * NEXT_PUBLIC_API_URL (or API_PUBLIC_URL).
 */
import { auth } from "@clerk/nextjs/server";

const SERVER_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + "/api/v1";
const BROWSER_BASE = "/api/backend";

export type ApiError = { code: string; message: string; status: number };

async function withAuth(): Promise<HeadersInit> {
  if (typeof window === "undefined") {
    const { getToken } = await auth();
    const token = await getToken();
    return token ? { Authorization: `Bearer ${token}` } : {};
  }
  // Browser: rely on Clerk's fetch wrapper attaching the session cookie via middleware.
  return {};
}

async function call<T>(method: string, path: string, body?: unknown): Promise<T> {
  const base = typeof window === "undefined" ? SERVER_BASE : BROWSER_BASE;
  const res = await fetch(base + path, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(await withAuth()),
    },
    body: body ? JSON.stringify(body) : undefined,
    cache: "no-store",
  });
  if (!res.ok) {
    const data = await res.json().catch(() => ({}));
    throw { code: data.code || "error", message: data.message || res.statusText, status: res.status } as ApiError;
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  get:    <T>(p: string) => call<T>("GET", p),
  post:   <T>(p: string, b?: unknown) => call<T>("POST", p, b),
  patch:  <T>(p: string, b?: unknown) => call<T>("PATCH", p, b),
  put:    <T>(p: string, b?: unknown) => call<T>("PUT", p, b),
  delete: <T>(p: string) => call<T>("DELETE", p),
};
