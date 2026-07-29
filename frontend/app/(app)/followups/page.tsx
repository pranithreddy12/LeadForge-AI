"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import type { PipelineLead } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { FollowupCard } from "@/components/followup-card";

/** Just the actionable follow-up queue: sent leads that have a follow-up ready to send.
 *  Reuses the /pipeline data + card; Pipeline shows everything, this shows only what
 *  needs sending right now. */
export default function FollowupsPage() {
  const qc = useQueryClient();
  const pipeline = useQuery({ queryKey: ["pipeline"], queryFn: () => api.get<{ leads: PipelineLead[] }>("/pipeline") });
  const refresh = useMutation({
    mutationFn: () => api.post<{ drafted: number }>("/pipeline/refresh"),
    onSuccess: (d: any) => {
      toast.success(`${d.drafted} follow-up${d.drafted === 1 ? "" : "s"} drafted`);
      qc.invalidateQueries({ queryKey: ["pipeline"] });
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });

  const ready = (pipeline.data?.leads ?? []).filter((l) => l.followups_ready.length > 0 && !l.replied);

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Follow-ups</h1>
          <p className="text-sm text-muted-foreground">
            Leads with a follow-up ready to send.
            {pipeline.data && <> · <span className="tabular-nums">{ready.length}</span> ready</>}
          </p>
        </div>
        <Button variant="outline" disabled={refresh.isPending} onClick={() => refresh.mutate()}
                title="Draft the day-3 / day-6 follow-ups now for any lead that's due.">
          {refresh.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Draft due follow-ups
        </Button>
      </div>

      {pipeline.isLoading && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {pipeline.data && ready.length === 0 && (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
          No follow-ups ready. They appear ~3 days after a lead is marked sent — or click <em>Draft due follow-ups</em>.
        </CardContent></Card>
      )}
      <div className="space-y-4">
        {ready.map((l) => <FollowupCard key={l.company_id} lead={l} />)}
      </div>
    </div>
  );
}
