"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Loader2, MessageSquare, Mail, Sparkles } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

import { api } from "@/lib/api";
import type { ReplyLead } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";

const STAGE_FLOW = ["replied", "in_conversation", "closed_won", "closed_lost"] as const;
const STAGE_LABEL: Record<string, string> = {
  replied: "Replied", in_conversation: "In conversation",
  closed_won: "Closed won", closed_lost: "Closed lost",
};

function fmt(ts?: string | null): string {
  if (!ts) return "—";
  return new Date(ts).toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function ChannelIcon({ channel }: { channel: string }) {
  return channel === "whatsapp"
    ? <MessageSquare className="h-3.5 w-3.5" />
    : <Mail className="h-3.5 w-3.5" />;
}

function ReplyCard({ r }: { r: ReplyLead }) {
  const qc = useQueryClient();
  const move = useMutation({
    mutationFn: (stage: string) => api.post(`/replies/${r.company_id}/stage`, { stage }),
    onSuccess: (_d, stage) => {
      toast.success(`Moved to ${STAGE_LABEL[stage] || stage}`);
      qc.invalidateQueries({ queryKey: ["replies"] });
    },
    onError: (e: any) => toast.error(e?.message || "Update failed"),
  });

  return (
    <Card>
      <CardContent className="space-y-3 pt-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <Link href={`/leads/${r.company_id}`} className="font-semibold hover:underline">
              {r.company_name}
            </Link>
            <div className="text-xs text-muted-foreground">{r.city || "—"}</div>
          </div>
          <div className="flex items-center gap-2">
            {r.score != null && (
              <span className="inline-flex items-center gap-1.5 text-sm">
                <span className="font-semibold tabular-nums">{r.score}</span>
                {r.grade && <Badge variant="brand">{r.grade}</Badge>}
              </span>
            )}
            <Badge variant="outline" className="inline-flex items-center gap-1">
              <ChannelIcon channel={r.channel} /> {r.channel}
            </Badge>
          </div>
        </div>

        <div className="grid gap-3 sm:grid-cols-2">
          <div className="rounded-md border border-white/5 bg-card/40 p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">Outreach sent</div>
            <p className="text-sm whitespace-pre-wrap text-muted-foreground">{r.original_message || "—"}</p>
          </div>
          <div className="rounded-md border border-white/5 bg-card/40 p-3">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground mb-1">
              Their reply · {fmt(r.reply_at)}
            </div>
            <p className="text-sm whitespace-pre-wrap">{r.reply_text || "—"}</p>
          </div>
        </div>

        {r.suggested_response && (
          <div className="rounded-md border border-brand-500/25 bg-brand-500/10 p-3">
            <div className="text-[11px] uppercase tracking-wide text-brand-200 mb-1 inline-flex items-center gap-1">
              <Sparkles className="h-3 w-3" /> Suggested response
            </div>
            <p className="text-sm whitespace-pre-wrap">{r.suggested_response}</p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2 pt-1">
          <span className="text-xs text-muted-foreground mr-1">Stage:</span>
          {STAGE_FLOW.map((s) => (
            <Button
              key={s}
              size="sm"
              variant={r.stage === s ? "default" : "outline"}
              disabled={move.isPending || r.stage === s}
              onClick={() => move.mutate(s)}
            >
              {STAGE_LABEL[s]}
            </Button>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

export default function RepliesPage() {
  const replies = useQuery({
    queryKey: ["replies"],
    queryFn: () => api.get<{ replies: ReplyLead[] }>("/replies"),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Replies</h1>
        <p className="text-sm text-muted-foreground">
          Everyone who replied — their message, an AI-suggested next response, and stage controls.
        </p>
      </div>
      {replies.isLoading && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {replies.data?.replies.length === 0 && (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
          No replies yet. When a prospect replies (email or WhatsApp) they show up here.
        </CardContent></Card>
      )}
      <div className="space-y-4">
        {replies.data?.replies.map((r) => <ReplyCard key={r.company_id} r={r} />)}
      </div>
    </div>
  );
}
