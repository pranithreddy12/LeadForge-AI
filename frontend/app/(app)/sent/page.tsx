"use client";

import { useMemo, useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Loader2, Mail, MessageCircle, Instagram, Linkedin, Phone, CheckCircle2, Reply, Send } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type SentItem = {
  id: string;
  company_id: string | null;
  company_name: string;
  channel: "email" | "whatsapp" | "instagram" | string;
  replied: boolean;
  subject: string | null;
  at: string;
};
type SentResp = { count: number; replied: number; items: SentItem[] };

const CHANNEL = {
  email: { icon: Mail, label: "Email", cls: "text-brand-300 border-brand-500/30 bg-brand-500/10" },
  whatsapp: { icon: MessageCircle, label: "WhatsApp", cls: "text-emerald-300 border-emerald-500/30 bg-emerald-500/10" },
  instagram: { icon: Instagram, label: "Instagram", cls: "text-fuchsia-300 border-fuchsia-500/30 bg-fuchsia-500/10" },
  linkedin: { icon: Linkedin, label: "LinkedIn", cls: "text-blue-300 border-blue-500/30 bg-blue-500/10" },
  phone: { icon: Phone, label: "Phone", cls: "text-sky-300 border-sky-500/30 bg-sky-500/10" },
} as const;

/** "Today" / "Yesterday" / "Mon, 14 Jul" bucket label for a timestamp. */
function dayLabel(iso: string): string {
  const d = new Date(iso);
  const now = new Date();
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((startOf(now) - startOf(d)) / 86400000);
  if (days === 0) return "Today";
  if (days === 1) return "Yesterday";
  return d.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", year: d.getFullYear() === now.getFullYear() ? undefined : "numeric" });
}
function timeLabel(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** One sent message + the inline "they replied → AI drafts your response" flow. */
function SentRow({ it }: { it: SentItem }) {
  const qc = useQueryClient();
  const c = CHANNEL[it.channel as keyof typeof CHANNEL] ?? CHANNEL.email;
  const Icon = c.icon;
  const [open, setOpen] = useState(false);
  const [text, setText] = useState("");
  const [suggested, setSuggested] = useState<string | null>(null);

  const logReply = useMutation({
    mutationFn: () => api.post<{ suggested_response: string | null; detail?: string }>(
      `/today/${it.company_id}/log-reply`, { their_message: text, channel: it.channel }),
    onSuccess: (d: any) => {
      setSuggested(d.suggested_response || null);
      toast.success(d.suggested_response ? "Reply logged — AI drafted your response" : (d.detail || "Reply logged"));
      qc.invalidateQueries({ queryKey: ["sent"] });
    },
    onError: (e: any) => toast.error(e?.message || "Failed to log reply"),
  });

  return (
    <div className="px-4 py-2.5 text-sm">
      <div className="flex items-center gap-3">
        <span className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[11px] ${c.cls}`}>
          <Icon className="h-3 w-3" /> {c.label}
        </span>
        {it.company_id
          ? <Link href={`/leads/${it.company_id}`} className="font-medium hover:underline truncate">{it.company_name}</Link>
          : <span className="font-medium truncate">{it.company_name}</span>}
        {it.subject && <span className="text-muted-foreground truncate hidden sm:inline">— {it.subject}</span>}
        <div className="flex-1" />
        {it.replied
          ? <span className="inline-flex items-center gap-1 text-[11px] text-emerald-400"><CheckCircle2 className="h-3 w-3" /> replied</span>
          : it.company_id && (
              <button onClick={() => { setOpen((v) => !v); setSuggested(null); }}
                      className="inline-flex items-center gap-1 text-[11px] text-brand-300 hover:text-brand-200">
                <Reply className="h-3 w-3" /> They replied
              </button>
          )}
        <span className="text-xs text-muted-foreground tabular-nums whitespace-nowrap">{timeLabel(it.at)}</span>
      </div>

      {open && !it.replied && (
        <div className="mt-2 rounded-md border border-emerald-500/25 bg-emerald-500/[0.05] p-3 space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-emerald-300">What did {it.company_name} reply?</div>
          <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3}
                    placeholder="Paste their reply here…"
                    className="w-full resize-y rounded-md border border-white/10 bg-background px-2.5 py-2 text-sm outline-none focus:border-emerald-400" />
          <Button size="sm" variant="default" disabled={!text.trim() || logReply.isPending} onClick={() => logReply.mutate()}>
            {logReply.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Draft my response
          </Button>
          {suggested && (
            <div className="rounded-md border border-brand-500/25 bg-brand-500/[0.06] p-3 space-y-1">
              <div className="text-[11px] uppercase tracking-wide text-brand-300">Suggested reply (edit before sending)</div>
              <p className="text-sm whitespace-pre-wrap">{suggested}</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function SentPage() {
  const q = useQuery({
    queryKey: ["sent"],
    queryFn: () => api.get<SentResp>("/sent"),
    refetchOnMount: "always",
  });

  // Group items by day label, preserving newest-first order.
  const groups = useMemo(() => {
    const out: { label: string; items: SentItem[] }[] = [];
    for (const it of q.data?.items ?? []) {
      const label = dayLabel(it.at);
      const g = out[out.length - 1];
      if (g && g.label === label) g.items.push(it);
      else out.push({ label, items: [it] });
    }
    return out;
  }, [q.data]);

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Sent</h1>
        <p className="text-sm text-muted-foreground">
          Every message you&apos;ve sent, by day and channel.
          {q.data && <> · <span className="tabular-nums">{q.data.count}</span> sent · <span className="tabular-nums text-emerald-400">{q.data.replied}</span> replied</>}
        </p>
      </div>

      {q.isLoading && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {q.data?.count === 0 && (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
          Nothing sent yet. Send from the <Link href="/today" className="text-brand-300 hover:underline">Today</Link> page, then mark it sent.
        </CardContent></Card>
      )}

      <div className="space-y-6">
        {groups.map((g) => (
          <div key={g.label} className="space-y-2">
            <div className="flex items-center gap-3">
              <div className="text-sm font-semibold">{g.label}</div>
              <div className="h-px flex-1 bg-white/10" />
              <div className="text-xs text-muted-foreground tabular-nums">{g.items.length}</div>
            </div>
            <Card>
              <CardContent className="p-0 divide-y divide-white/5">
                {g.items.map((it) => <SentRow key={it.id} it={it} />)}
              </CardContent>
            </Card>
          </div>
        ))}
      </div>
    </div>
  );
}
