"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { Activity } from "lucide-react";

import { api } from "@/lib/api";
import type { Page as PageT, Signal, SignalKind } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { timeAgo } from "@/lib/utils";

const KINDS: SignalKind[] = [
  "hiring", "funding", "growth", "product_launch", "tech_install",
  "leadership_change", "partnership", "news", "traffic_growth", "office_expansion",
];

export default function SignalsPage() {
  const [kind, setKind] = useState<SignalKind | null>(null);
  const { data } = useQuery({
    queryKey: ["signals-all", kind],
    queryFn: () => api.get<PageT<Signal>>(`/signals?page_size=100${kind ? `&kind=${kind}` : ""}`),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Buying signals</h1>
        <p className="text-sm text-muted-foreground">Activity across your accounts.</p>
      </div>

      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setKind(null)}
          className={"rounded-md px-2.5 py-1 text-xs border " +
            (kind === null ? "border-brand-500/40 bg-brand-500/15 text-brand-200" : "border-white/10 bg-card/30 text-muted-foreground hover:text-foreground")}
        >All</button>
        {KINDS.map(k => (
          <button key={k} onClick={() => setKind(k)}
            className={"rounded-md px-2.5 py-1 text-xs border " +
              (kind === k ? "border-brand-500/40 bg-brand-500/15 text-brand-200" : "border-white/10 bg-card/30 text-muted-foreground hover:text-foreground")}>
            {k}
          </button>
        ))}
      </div>

      <Card>
        <CardHeader><CardTitle>{data?.total ?? 0} signals</CardTitle></CardHeader>
        <CardContent className="p-0">
          {data && data.items.length > 0 ? (
            <ul>
              {data.items.map(s => (
                <li key={s.id} className="border-b border-white/5 px-5 py-3 flex items-start gap-3">
                  <Activity className="h-4 w-4 text-brand-400 mt-0.5" />
                  <Badge variant={
                    s.kind === "funding" ? "success" :
                    s.kind === "hiring" ? "info" :
                    s.kind === "product_launch" ? "brand" :
                    "default"
                  }>{s.kind}</Badge>
                  <div className="flex-1 min-w-0">
                    <Link href={`/leads/${s.company_id}`} className="font-medium text-sm hover:underline">{s.label}</Link>
                    {s.description && <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{s.description}</div>}
                  </div>
                  <div className="text-xs text-muted-foreground">{timeAgo(s.created_at)}</div>
                </li>
              ))}
            </ul>
          ) : (
            <div className="p-8 text-center text-sm text-muted-foreground">No signals yet.</div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
