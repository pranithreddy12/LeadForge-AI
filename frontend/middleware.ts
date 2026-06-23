import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";
import { clerkConfigured } from "@/lib/clerk-config";

const isPublic = createRouteMatcher([
  "/",
  "/pricing",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/api/health",
]);

// Dev fallback: when Clerk isn't configured (placeholder keys), don't run the
// Clerk middleware — it would crash on every request. In demo mode the backend
// seats every request as the seeded demo user, so authed pages render fine.
const handler = clerkConfigured
  ? clerkMiddleware(async (auth, req) => {
      if (!isPublic(req)) {
        await auth.protect();
      }
    })
  : (_req: NextRequest) => NextResponse.next();

export default handler;

export const config = {
  matcher: ["/((?!_next|.*\\..*).*)", "/(api|trpc)(.*)"],
};
