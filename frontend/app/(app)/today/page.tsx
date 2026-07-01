"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Copy, Loader2, RefreshCw, SkipForward } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

import { api } from "@/lib/api";
import type { TodayLead } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const SKIP_REASONS = [
  ["bad_fit", "Bad fit"],
  ["no_contact", "No contact info"],
  ["looks_wrong", "Looks wrong"],
  ["other", "Other"],
] as const;

function CopyBtn({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return (
    <Button
      size="sm" variant="outline"
      onClick={async () => {
        try { await navigator.clipboard.writeText(text); setDone(true); toast.success(`${label} copied`); setTimeout(() => setDone(false), 1500); }
        catch { toast.error("Copy failed"); }
      }}
    >
      {done ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />} {label}
    </Button>
  );
}

function LeadCard({ lead }: { lead: TodayLead }) {
  const qc = useQueryClient();
  const [skipOpen, setSkipOpen] = useState(false);
  const invalidate = () => qc.invalidateQueries({ queryKey: ["today"] });

  const sent = useMutation({
    mutationFn: () => api.post(`/today/${lead.company_id}/sent`),
    onSuccess: () => { toast.success("Marked as sent"); invalidate(); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });
  const skip = useMutation({
    mutationFn: (reason: string) => api.post(`/today/${lead.company_id}/skip`, { reason }),
    onSuccess: () => { toast("Skipped"); invalidate(); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });

  return (
    <Card>
      <CardContent className="space-y-3 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <Link href={`/leads/${lead.company_id}`} className="font-semibold hover:underline">{lead.company_name}</Link>
            <div className="text-xs text-muted-foreground">{lead.domain || "—"}</div>
          </div>
          <div className="flex items-center gap-2">
            {lead.score != null && (
              <span className="inline-flex items-center gap-1.5 text-sm">
                <span className="font-semibold tabular-nums">{lead.score}</span>
                {lead.grade && <Badge variant="brand">{lead.grade}</Badge>}
              </span>
            )}
          </div>
        </div>

        {lead.signal && (
          <div className="text-xs">
            <span className="text-muted-foreground">Why it qualified: </span>
            <span className="text-brand-200">{lead.signal}</span>
          </div>
        )}

        <div className="rounded-md border border-white/5 bg-card/40 p-3 space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Drafted email</div>
          <div className="text-sm"><span className="text-muted-foreground">To:</span> {lead.to || <span className="text-amber-500">no email found</span>}</div>
          <div className="text-sm"><span className="text-muted-foreground">Subject:</span> {lead.subject}</div>
          <p className="text-sm whitespace-pre-wrap pt-1 border-t border-white/5">{lead.body}</p>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <CopyBtn text={lead.subject} label="Copy subject" />
          <CopyBtn text={lead.body} label="Copy body" />
          {lead.to && <CopyBtn text={lead.to} label="Copy email" />}
          <div className="flex-1" />
          <Button size="sm" variant="default" disabled={sent.isPending} onClick={() => sent.mutate()}>
            {sent.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Mark as sent
          </Button>
          {!skipOpen ? (
            <Button size="sm" variant="outline" onClick={() => setSkipOpen(true)}>
              <SkipForward className="h-3.5 w-3.5" /> Skip
            </Button>
          ) : (
            <div className="flex items-center gap-1">
              {SKIP_REASONS.map(([v, label]) => (
                <Button key={v} size="sm" variant="outline" disabled={skip.isPending} onClick={() => skip.mutate(v)}>{label}</Button>
              ))}
            </div>
          )}
        </div>
      </CardContent>
    </Card>
  );
}

export default function TodayPage() {
  const qc = useQueryClient();
  const today = useQuery({
    queryKey: ["today"],
    queryFn: () => api.get<{ mode: string; count: number; leads: TodayLead[] }>("/today"),
  });

  const run = useMutation({
    mutationFn: () => api.post<{ count: number }>("/today/run"),
    onSuccess: (d: any) => {
      toast.success(`Discovery started (${d.count} workflow${d.count === 1 ? "" : "s"}). Drafts appear here in a couple of minutes — refresh.`);
      setTimeout(() => qc.invalidateQueries({ queryKey: ["today"] }), 4000);
    },
    onError: (e: any) => toast.error(e?.message || "Failed to start"),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Today&apos;s Leads</h1>
          <p className="text-sm text-muted-foreground">
            Review each draft, copy it, send it yourself, then mark it sent.
            {today.data && <> Mode: <Badge variant={today.data.mode === "manual" ? "brand" : "outline"}>{today.data.mode}</Badge></>}
          </p>
        </div>
        <Button variant="glow" disabled={run.isPending} onClick={() => run.mutate()}>
          {run.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Run Today&apos;s Discovery
        </Button>
      </div>

      {today.isLoading && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {today.data?.count === 0 && (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
          No drafts waiting. Click <em>Run Today&apos;s Discovery</em> to find + draft today&apos;s leads (give it a minute, then refresh).
        </CardContent></Card>
      )}
      <div className="space-y-4">
        {today.data?.leads.map((l) => <LeadCard key={l.draft_id} lead={l} />)}
      </div>
    </div>
  );
}
