/**
 * LeadForge API client.
 *
 * On the browser we route through Next.js' `/api/backend/*` rewrite (see next.config.mjs),
 * which proxies to FastAPI under /api/v1. On the server we hit the API directly via
 * NEXT_PUBLIC_API_URL (or API_PUBLIC_URL).
 */
import { clerkConfigured } from "./clerk-config";

const SERVER_BASE = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000") + "/api/v1";
const BROWSER_BASE = "/api/backend";

export type ApiError = { code: string; message: string; status: number };

async function withAuth(): Promise<HeadersInit> {
  // Demo mode: no Clerk → no token. The backend's dev-auth bypass seats the
  // request as the seeded demo user, so unauthenticated calls succeed.
  if (!clerkConfigured) return {};

  // Browser with Clerk: pull the session token from the CLIENT SDK. We must NOT
  // import "@clerk/nextjs/server" here — this module is imported by client
  // components, and the server entry pulls in "server-only", which breaks the
  // production build. The Clerk client global is the client-safe source.
  if (typeof window !== "undefined") {
    try {
      const token = await (
        window as unknown as { Clerk?: { session?: { getToken?: () => Promise<string | null> } } }
      ).Clerk?.session?.getToken?.();
      return token ? { Authorization: `Bearer ${token}` } : {};
    } catch {
      return {};
    }
  }
  // Server context: proxied calls rely on the middleware/session cookie.
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
