"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard, Sparkles, Building2, Users, Activity, Target,
  Workflow as WorkflowIcon, MessageSquare, Settings, Send, CreditCard,
} from "lucide-react";
import { cn } from "@/lib/utils";

const nav = [
  { href: "/dashboard",  label: "Dashboard",  icon: LayoutDashboard },
  { href: "/icp",        label: "AI ICP",     icon: Sparkles },
  { href: "/leads",      label: "Leads",      icon: Building2 },
  { href: "/contacts",   label: "Contacts",   icon: Users },
  { href: "/signals",    label: "Signals",    icon: Activity },
  { href: "/crm",        label: "CRM",        icon: Target },
  { href: "/campaigns",  label: "Campaigns",  icon: Send },
  { href: "/workflows",  label: "Workflows",  icon: WorkflowIcon },
  { href: "/chat",       label: "Ask AI",     icon: MessageSquare },
];

const footerNav = [
  { href: "/billing",   label: "Billing",  icon: CreditCard },
  { href: "/settings",  label: "Settings", icon: Settings },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="hidden lg:flex h-screen w-60 flex-col border-r border-white/5 bg-card/30 backdrop-blur-xl">
      <div className="flex h-14 items-center gap-2 px-5 border-b border-white/5">
        <div className="relative flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 shadow-glow">
          <Sparkles className="h-4 w-4 text-white" />
        </div>
        <span className="font-semibold tracking-tight">LeadForge</span>
        <span className="text-[10px] px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-muted-foreground">AI</span>
      </div>

      <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto scrollbar-thin">
        {nav.map((n) => {
          const Icon = n.icon;
          const active = pathname === n.href || pathname?.startsWith(n.href + "/");
          return (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" /> {n.label}
            </Link>
          );
        })}
      </nav>

      <div className="px-3 pb-4 space-y-0.5 border-t border-white/5 pt-3">
        {footerNav.map((n) => {
          const Icon = n.icon;
          const active = pathname === n.href;
          return (
            <Link
              key={n.href}
              href={n.href}
              className={cn(
                "flex items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                active
                  ? "bg-secondary text-foreground"
                  : "text-muted-foreground hover:bg-secondary/60 hover:text-foreground"
              )}
            >
              <Icon className="h-4 w-4" /> {n.label}
            </Link>
          );
        })}
      </div>
    </aside>
  );
}
