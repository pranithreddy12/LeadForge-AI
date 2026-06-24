"use client";

import Link from "next/link";
import { Activity, Banknote, UserPlus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { timeAgo } from "@/lib/utils";

export interface SignalFeedItem {
  id: string;
  company_id: string;
  company_name: string;
  company_domain?: string | null;
  kind: string;
  label: string;
  severity: number;
  confidence: number;
  url?: string | null;
  created_at: string;
}

const KIND_BADGE: Record<string, "success" | "info" | "brand" | "warn" | "default"> = {
  funding: "success", hiring: "info", product_launch: "brand",
  leadership_change: "warn", tech_install: "default", growth: "info",
};

export function SignalFeed({ items, emptyHint }: { items: SignalFeedItem[]; emptyHint: string }) {
  if (!items || items.length === 0) {
    return <div className="px-5 py-8 text-center text-sm text-muted-foreground">{emptyHint}</div>;
  }
  return (
    <ul className="divide-y divide-white/5">
      {items.map((s) => (
        <li key={s.id} className="flex items-start gap-3 px-5 py-2.5">
          <Badge variant={KIND_BADGE[s.kind] || "default"} className="shrink-0 mt-0.5">{s.kind.replace("_", " ")}</Badge>
          <div className="min-w-0 flex-1">
            <div className="text-sm truncate">{s.label}</div>
            <Link href={`/leads/${s.company_id}`} className="text-xs text-brand-300 hover:underline">
              {s.company_name}
            </Link>
          </div>
          <div className="text-[11px] text-muted-foreground shrink-0">{timeAgo(s.created_at)}</div>
        </li>
      ))}
    </ul>
  );
}

export const FeedIcon = { activity: Activity, funding: Banknote, exec: UserPlus };
