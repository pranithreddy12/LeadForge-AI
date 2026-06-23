"use client";

import { useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Building2 } from "lucide-react";

import { api } from "@/lib/api";
import type { Company, Page as PageT, PipelineStage } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

const STAGES: PipelineStage[] = [
  "new", "qualified", "contacted", "replied", "meeting", "proposal", "won", "lost",
];

export default function CRMPage() {
  const { data } = useQuery({
    queryKey: ["companies-crm"],
    queryFn: () => api.get<PageT<Company>>("/companies?page_size=200"),
  });

  const byStage = useMemo(() => {
    const m: Record<PipelineStage, Company[]> = Object.fromEntries(STAGES.map(s => [s, []])) as any;
    (data?.items || []).forEach(c => { m[c.pipeline_stage]?.push(c); });
    return m;
  }, [data]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">CRM</h1>
        <p className="text-sm text-muted-foreground">Pipeline of every account in your workspace.</p>
      </div>

      <div className="flex gap-3 overflow-x-auto pb-4 -mx-1 px-1">
        {STAGES.map(stage => (
          <div key={stage} className="w-72 shrink-0">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-xs font-medium uppercase tracking-wider text-muted-foreground">{stage}</div>
              <Badge variant="outline">{byStage[stage].length}</Badge>
            </div>
            <div className="space-y-2">
              {byStage[stage].slice(0, 30).map(c => (
                <Link key={c.id} href={`/leads/${c.id}`}>
                  <Card className="hover:bg-white/[0.04] transition-colors">
                    <CardContent className="p-3 flex items-center gap-2.5">
                      <div className="flex h-7 w-7 items-center justify-center rounded-md bg-white/5 text-muted-foreground">
                        <Building2 className="h-3.5 w-3.5" />
                      </div>
                      <div className="min-w-0">
                        <div className="text-sm font-medium truncate">{c.name}</div>
                        <div className="text-[11px] text-muted-foreground truncate">{c.industry || c.domain || "—"}</div>
                      </div>
                    </CardContent>
                  </Card>
                </Link>
              ))}
              {byStage[stage].length === 0 && (
                <div className="rounded-md border border-dashed border-white/10 p-3 text-xs text-muted-foreground text-center">empty</div>
              )}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
