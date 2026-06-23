"use client";

import { UserButton, OrganizationSwitcher } from "@clerk/nextjs";
import { Search, Sparkles, Command } from "lucide-react";
import { Input } from "@/components/ui/input";
import { clerkConfigured } from "@/lib/clerk-config";

export function Topbar() {
  return (
    <header className="sticky top-0 z-30 flex h-14 items-center gap-3 border-b border-white/5 bg-background/60 backdrop-blur-xl px-4 lg:px-6">
      <div className="relative flex-1 max-w-xl">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
        <Input
          placeholder="Search companies, contacts, signals…"
          className="pl-9 pr-12 h-9 bg-card/40"
        />
        <kbd className="absolute right-3 top-1/2 -translate-y-1/2 hidden md:flex items-center gap-1 rounded border border-white/10 px-1.5 py-0.5 text-[10px] text-muted-foreground">
          <Command className="h-3 w-3" /> K
        </kbd>
      </div>

      <button className="hidden md:flex items-center gap-2 rounded-md border border-white/10 bg-card/40 px-3 py-1.5 text-xs text-muted-foreground hover:text-foreground">
        <Sparkles className="h-3.5 w-3.5 text-brand-400" /> Ask AI
      </button>

      {clerkConfigured ? (
        <>
          <OrganizationSwitcher
            appearance={{ elements: { rootBox: "h-9", organizationSwitcherTrigger: "h-9 px-2" } }}
            afterCreateOrganizationUrl="/dashboard"
            afterSelectOrganizationUrl="/dashboard"
          />
          <UserButton appearance={{ elements: { userButtonAvatarBox: "h-8 w-8" } }} />
        </>
      ) : (
        <DemoUserChip />
      )}
    </header>
  );
}

/** Stand-in for the Clerk user/org widgets when running in demo mode. */
function DemoUserChip() {
  return (
    <div className="flex items-center gap-2">
      <span className="hidden sm:inline-flex items-center gap-1 rounded-md border border-amber-500/30 bg-amber-500/10 px-2 py-1 text-[11px] text-amber-300">
        Demo mode
      </span>
      <div className="flex items-center gap-2 rounded-md border border-white/10 bg-card/40 px-2 py-1">
        <div className="flex h-6 w-6 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-[11px] font-semibold text-white">
          DF
        </div>
        <span className="hidden sm:inline text-xs text-muted-foreground">Demo Founder</span>
      </div>
    </div>
  );
}
