"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { Check, Loader2, Send } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

import { api } from "@/lib/api";
import type { PipelineLead } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

/** One sent lead + its ready follow-ups, with Send / Mark-sent. Shared by /pipeline
 *  (all sent leads) and /followups (only leads with a ready follow-up). */
export function FollowupCard({ lead }: { lead: PipelineLead }) {
  const qc = useQueryClient();
  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["pipeline"] });
    qc.invalidateQueries({ queryKey: ["notifications"] });
  };
  const sent = useMutation({
    mutationFn: (draftId: string) => api.post(`/pipeline/${draftId}/sent`),
    onSuccess: () => { toast.success("Follow-up marked sent"); invalidate(); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });
  const send = useMutation({
    mutationFn: (draftId: string) => api.post<{ sent: boolean; to?: string; reason?: string; detail?: string }>(`/pipeline/${draftId}/send-email`),
    onSuccess: (d: any) => {
      if (d.sent) { toast.success(`Sent to ${d.to}`); invalidate(); }
      else toast.error(d.detail || d.reason || "Could not send");
    },
    onError: (e: any) => toast.error(e?.message || "Send failed"),
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
              {f.to && (
                <Button size="sm" variant="glow" disabled={send.isPending}
                        title={`Send this follow-up now to ${f.to} from your configured Gmail`}
                        onClick={() => { if (confirm(`Send this follow-up now to ${f.to}?\n\nThis sends a real email from your configured account. It can't be unsent.`)) send.mutate(f.draft_id); }}>
                  {send.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Send email
                </Button>
              )}
              <Button size="sm" variant="outline" disabled={sent.isPending} onClick={() => sent.mutate(f.draft_id)}
                      title="I sent this follow-up myself (or on another channel) — just take it off the queue.">
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
