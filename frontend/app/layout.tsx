import type { Metadata } from "next";
import { Inter, JetBrains_Mono } from "next/font/google";
import { ClerkProvider } from "@clerk/nextjs";
import { Providers } from "@/components/providers";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], variable: "--font-sans", display: "swap" });
const mono = JetBrains_Mono({ subsets: ["latin"], variable: "--font-mono", display: "swap" });

export const metadata: Metadata = {
  title: "LeadForge AI — find the accounts most likely to buy now",
  description:
    "AI-powered lead discovery, validation, and opportunity intelligence for B2B sellers.",
};

const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
const clerkConfigured =
  clerkKey.startsWith("pk_") && !clerkKey.endsWith("xxx") && !clerkKey.endsWith("placeholder");

export default function RootLayout({ children }: { children: React.ReactNode }) {
  const tree = (
    <html lang="en" className={`${inter.variable} ${mono.variable} dark`} suppressHydrationWarning>
      <body>
        <Providers>{children}</Providers>
      </body>
    </html>
  );

  if (!clerkConfigured) {
    // Dev fallback: render the marketing page without Clerk. App routes that
    // rely on Clerk hooks will surface their own errors until real keys are set.
    return tree;
  }

  return (
    <ClerkProvider
      appearance={{
        variables: {
          colorPrimary: "#3a5dff",
          colorBackground: "#0a0d18",
          colorText: "#f3f5f8",
          colorTextSecondary: "#9aa3b2",
        },
      }}
    >
      {tree}
    </ClerkProvider>
  );
}
