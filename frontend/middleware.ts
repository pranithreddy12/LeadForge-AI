import { clerkMiddleware, createRouteMatcher } from "@clerk/nextjs/server";
import type { NextRequest } from "next/server";
import { NextResponse } from "next/server";

const isPublic = createRouteMatcher([
  "/",
  "/pricing",
  "/sign-in(.*)",
  "/sign-up(.*)",
  "/api/health",
]);

// Dev fallback: when Clerk isn't configured (placeholder keys), don't run the
// Clerk middleware — it would crash on every request. The marketing page still
// renders; authed routes will surface their own "Clerk not configured" error.
const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
const clerkConfigured =
  clerkKey.startsWith("pk_") && !clerkKey.endsWith("xxx") && !clerkKey.endsWith("placeholder");

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
