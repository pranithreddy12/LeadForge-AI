"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

import { api } from "@/lib/api";
import type { PipelineLead } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

function LeadRow({ lead }: { lead: PipelineLead }) {
  const qc = useQueryClient();
  const sent = useMutation({
    mutationFn: (draftId: string) => api.post(`/pipeline/${draftId}/sent`),
    onSuccess: () => { toast.success("Follow-up marked sent"); qc.invalidateQueries({ queryKey: ["pipeline"] }); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });

  return (
    <Card>
      <CardContent className="space-y-3 pt-5">
        <div className="flex items-center justify-between gap-3">
          <Link href={`/leads/${lead.company_id}`} className="font-semibold hover:underline">{lead.company_name}</Link>
          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground">sent {lead.sent_days_ago}d ago</span>
            {lead.replied
              ? <Badge variant="brand">replied</Badge>
              : lead.followups_ready.length > 0
                ? <Badge variant="brand">Follow-up ready</Badge>
                : <Badge variant="outline">waiting</Badge>}
          </div>
        </div>

        {lead.followups_ready.map((f) => (
          <div key={f.draft_id} className="rounded-md border border-brand-500/20 bg-brand-500/[0.06] p-3 space-y-2">
            <div className="text-[11px] uppercase tracking-wide text-brand-200">
              Follow-up {f.step === 2 ? "#1 (day 3)" : "#2 (day 6)"}
            </div>
            <div className="text-sm"><span className="text-muted-foreground">To:</span> {f.to || <span className="text-amber-500">no email</span>}</div>
            <div className="text-sm"><span className="text-muted-foreground">Subject:</span> {f.subject}</div>
            <p className="text-sm whitespace-pre-wrap pt-1 border-t border-white/5">{f.body}</p>
            <div className="flex flex-wrap items-center gap-2 pt-1">
              <div className="flex-1" />
              <Button size="sm" disabled={sent.isPending} onClick={() => sent.mutate(f.draft_id)}>
                {sent.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Mark sent
              </Button>
            </div>
          </div>
        ))}
        {lead.followups_ready.length === 0 && !lead.replied && (
          <p className="text-xs text-muted-foreground">No follow-up due yet (day 3 / day 6).</p>
        )}
      </CardContent>
    </Card>
  );
}

export default function PipelinePage() {
  const qc = useQueryClient();
  const pipeline = useQuery({ queryKey: ["pipeline"], queryFn: () => api.get<{ leads: PipelineLead[] }>("/pipeline") });
  const refresh = useMutation({
    mutationFn: () => api.post<{ drafted: number }>("/pipeline/refresh"),
    onSuccess: (d: any) => { toast.success(`${d.drafted} follow-up${d.drafted === 1 ? "" : "s"} drafted`); qc.invalidateQueries({ queryKey: ["pipeline"] }); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Pipeline</h1>
          <p className="text-sm text-muted-foreground">Sent leads and their day-3 / day-6 follow-ups, ready to review and send.</p>
        </div>
        <Button variant="outline" disabled={refresh.isPending} onClick={() => refresh.mutate()}>
          {refresh.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Draft due follow-ups
        </Button>
      </div>
      {pipeline.isLoading && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {pipeline.data?.leads.length === 0 && (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
          Nothing here yet. Mark leads as sent on the Today page; follow-ups appear after 3 days.
        </CardContent></Card>
      )}
      <div className="space-y-4">
        {pipeline.data?.leads.map((l) => <LeadRow key={l.company_id} lead={l} />)}
      </div>
    </div>
  );
}
