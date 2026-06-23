/**
 * Single source of truth for "is Clerk configured?".
 *
 * When the publishable key is a placeholder (pk_test_xxx) or missing, the whole
 * app runs in demo mode: no ClerkProvider, no auth UI, and the backend's
 * dev-auth bypass seats every request as the seeded demo user.
 */
export const CLERK_PUBLISHABLE_KEY = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";

export const clerkConfigured =
  CLERK_PUBLISHABLE_KEY.startsWith("pk_") &&
  !CLERK_PUBLISHABLE_KEY.endsWith("xxx") &&
  !CLERK_PUBLISHABLE_KEY.endsWith("placeholder");
