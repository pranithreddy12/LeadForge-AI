"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Bell, Send, Clock } from "lucide-react";

import { api } from "@/lib/api";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
} from "@/components/ui/dropdown-menu";

type Notif = {
  id: string;
  type: "followup_ready" | "followup_due";
  company_id: string;
  company_name: string;
  title: string;
  detail: string;
  days_ago: number;
  href: string;
};
type NotifResp = { count: number; ready: number; due: number; items: Notif[] };

export function NotificationBell() {
  // Poll every couple of minutes so new follow-ups surface without a refresh.
  const q = useQuery({
    queryKey: ["notifications"],
    queryFn: () => api.get<NotifResp>("/notifications"),
    refetchInterval: 120_000,
    refetchOnWindowFocus: true,
  });
  const data = q.data;
  const count = data?.count ?? 0;

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <button className="relative flex h-9 w-9 items-center justify-center rounded-md border border-white/10 bg-card/40 text-muted-foreground hover:text-foreground transition-colors"
                aria-label="Notifications" title="Follow-up notifications">
          <Bell className="h-4 w-4" />
          {count > 0 && (
            <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-brand-500 px-1 text-[10px] font-semibold text-white">
              {count > 9 ? "9+" : count}
            </span>
          )}
        </button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end"
        className="w-80 max-h-[70vh] overflow-y-auto p-0">
        <div className="flex items-center justify-between border-b border-white/10 px-3 py-2">
          <span className="text-sm font-medium">Notifications</span>
          {data && count > 0 && (
            <span className="text-[11px] text-muted-foreground">
              {data.ready} ready · {data.due} due
            </span>
          )}
        </div>

        {count === 0 ? (
          <div className="px-3 py-8 text-center text-sm text-muted-foreground">
            <Bell className="mx-auto mb-2 h-5 w-5 opacity-40" />
            You&apos;re all caught up — no follow-ups pending.
          </div>
        ) : (
          <div className="divide-y divide-white/5">
            {data!.items.map((n) => {
              const Icon = n.type === "followup_ready" ? Send : Clock;
              const tone = n.type === "followup_ready" ? "text-brand-300" : "text-amber-400";
              return (
                <Link key={n.id} href={n.href}
                      className="flex gap-2.5 px-3 py-2.5 text-sm hover:bg-white/[0.03] transition-colors">
                  <Icon className={`mt-0.5 h-4 w-4 shrink-0 ${tone}`} />
                  <div className="min-w-0">
                    <div className="truncate font-medium">{n.title}</div>
                    <div className="truncate text-xs text-muted-foreground">{n.detail}</div>
                  </div>
                </Link>
              );
            })}
          </div>
        )}

        {count > 0 && (
          <Link href="/followups"
                className="block border-t border-white/10 px-3 py-2 text-center text-xs text-brand-300 hover:text-brand-200">
            Open Follow-ups
          </Link>
        )}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
