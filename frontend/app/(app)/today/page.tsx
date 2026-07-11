"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Ban, Check, Clock, Copy, Facebook, Instagram, Linkedin, Loader2, MessageCircle, Music2,
  RefreshCw, Send, SkipForward, Youtube,
} from "lucide-react";
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

const SOCIAL_META: Record<string, { label: string; Icon: any; cls: string }> = {
  instagram: { label: "Instagram", Icon: Instagram, cls: "border-pink-500/30 bg-pink-500/10 text-pink-300 hover:bg-pink-500/20" },
  facebook:  { label: "Facebook",  Icon: Facebook,  cls: "border-blue-500/30 bg-blue-500/10 text-blue-300 hover:bg-blue-500/20" },
  linkedin:  { label: "LinkedIn",  Icon: Linkedin,  cls: "border-sky-500/30 bg-sky-500/10 text-sky-300 hover:bg-sky-500/20" },
  tiktok:    { label: "TikTok",    Icon: Music2,    cls: "border-white/20 bg-white/5 text-foreground hover:bg-white/10" },
  youtube:   { label: "YouTube",   Icon: Youtube,   cls: "border-red-500/30 bg-red-500/10 text-red-300 hover:bg-red-500/20" },
  whatsapp:  { label: "Site WhatsApp", Icon: MessageCircle, cls: "border-emerald-500/30 bg-emerald-500/10 text-emerald-300 hover:bg-emerald-500/20" },
};

function SocialPills({ socials }: { socials?: Record<string, string> }) {
  if (!socials) return null;
  const entries = Object.entries(socials).filter(([k, v]) => v && SOCIAL_META[k]);
  if (entries.length === 0) return null;
  return (
    <>
      {entries.map(([k, url]) => {
        const { label, Icon, cls } = SOCIAL_META[k];
        return (
          <a key={k} href={url} target="_blank" rel="noopener noreferrer" title={url}
             className={`inline-flex items-center gap-1 rounded-md border px-2 py-0.5 transition-colors ${cls}`}>
            <Icon className="h-3.5 w-3.5" /> {label}
          </a>
        );
      })}
    </>
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
  const optout = useMutation({
    mutationFn: () => api.post<{ identifiers_suppressed: number }>(`/today/${lead.company_id}/optout`),
    onSuccess: (d: any) => { toast.success(`Opted out (${d.identifiers_suppressed} identifier${d.identifiers_suppressed === 1 ? "" : "s"} suppressed). Won't be contacted again.`); invalidate(); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });
  const sendEmail = useMutation({
    mutationFn: () => api.post<{ sent: boolean; to?: string; reason?: string; detail?: string }>(`/today/${lead.company_id}/send-email`),
    onSuccess: (d: any) => {
      if (d.sent) { toast.success(`Sent to ${d.to}`); invalidate(); }
      else toast.error(d.detail || d.reason || "Could not send");
    },
    onError: (e: any) => toast.error(e?.message || "Send failed"),
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

        <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs">
          {lead.phone && (
            lead.wa_link
              ? <a href={lead.wa_link} target="_blank" rel="noopener noreferrer"
                   className="inline-flex items-center gap-1 rounded-md border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-emerald-300 hover:bg-emerald-500/20 transition-colors"
                   title="Open WhatsApp chat">
                  <MessageCircle className="h-3.5 w-3.5" /> {lead.phone}
                </a>
              : <span className="text-muted-foreground">📞 {lead.phone}</span>
          )}
          <SocialPills socials={lead.socials} />
          {lead.decision_maker && <span className="text-brand-200">👤 {lead.decision_maker}</span>}
          {lead.to && (
            <span className="inline-flex items-center gap-1.5">
              <span className={`h-2 w-2 rounded-full ${lead.email_mx_ok === true ? "bg-green-500" : lead.email_mx_ok === false ? "bg-red-500" : "bg-white/30"}`} />
              <span className="text-muted-foreground">
                MX {lead.email_mx_ok === true ? "valid" : lead.email_mx_ok === false ? "INVALID" : "unknown"}
              </span>
            </span>
          )}
        </div>

        {lead.spam_flags && lead.spam_flags.length > 0 && (
          <div className="rounded-md border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-400">
            ⚠ Spam-risk: {lead.spam_flags.join(" · ")}
          </div>
        )}

        <div className="rounded-md border border-white/5 bg-card/40 p-3 space-y-2">
          <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Drafted email</div>
          <div className="text-sm"><span className="text-muted-foreground">To:</span> {lead.to || <span className="text-amber-500">no email found</span>}</div>
          <div className="text-sm"><span className="text-muted-foreground">Subject:</span> {lead.subject}</div>
          <p className="text-sm whitespace-pre-wrap pt-1 border-t border-white/5">{lead.body}</p>
        </div>

        {lead.dm && (
          <div className="rounded-md border border-emerald-500/20 bg-emerald-500/[0.06] p-3 space-y-1">
            <div className="text-[11px] uppercase tracking-wide text-emerald-300">WhatsApp / DM variant</div>
            <p className="text-sm whitespace-pre-wrap">{lead.dm}</p>
          </div>
        )}

        {lead.dm_ar && (
          <div className="rounded-md border border-sky-500/20 bg-sky-500/[0.06] p-3 space-y-1">
            <div className="text-[11px] uppercase tracking-wide text-sky-300">Arabic DM (العربية)</div>
            <p className="text-sm whitespace-pre-wrap" dir="rtl" lang="ar">{lead.dm_ar}</p>
          </div>
        )}

        {lead.auto_reply_comeback && (
          <div className="rounded-md border border-amber-500/20 bg-amber-500/[0.06] p-3 space-y-1">
            <div className="text-[11px] uppercase tracking-wide text-amber-300">If they auto-reply (send this back)</div>
            <p className="text-sm whitespace-pre-wrap">{lead.auto_reply_comeback}</p>
          </div>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <CopyBtn text={lead.subject} label="Copy subject" />
          <CopyBtn text={lead.body} label="Copy body" />
          {lead.dm && <CopyBtn text={lead.dm} label="Copy DM" />}
          {lead.dm_ar && <CopyBtn text={lead.dm_ar} label="Copy Arabic DM" />}
          {lead.auto_reply_comeback && <CopyBtn text={lead.auto_reply_comeback} label="Copy comeback" />}
          {lead.to && <CopyBtn text={lead.to} label="Copy email" />}
          <div className="flex-1" />
          {lead.to && (
            <Button size="sm" variant="glow" disabled={sendEmail.isPending}
                    title={`Send this draft now to ${lead.to} from your configured Gmail`}
                    onClick={() => { if (confirm(`Send this email now to ${lead.to}?\n\nThis sends a real email from your configured account. It can't be unsent.`)) sendEmail.mutate(); }}>
              {sendEmail.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Send email
            </Button>
          )}
          <Button size="sm" variant="default" disabled={sent.isPending} onClick={() => sent.mutate()}
                  title="I sent this myself (e.g. via WhatsApp) — just log it, don't send from the app">
            {sent.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} Mark as sent
          </Button>
          {!skipOpen ? (
            <>
              <Button size="sm" variant="outline" onClick={() => setSkipOpen(true)}>
                <SkipForward className="h-3.5 w-3.5" /> Skip
              </Button>
              <Button size="sm" variant="ghost" className="text-red-400 hover:text-red-300"
                      disabled={optout.isPending}
                      title="They asked not to be contacted (or bad target): add to do-not-contact list, exclude permanently."
                      onClick={() => { if (confirm(`Opt out ${lead.company_name}? They'll be permanently excluded from all future outreach.`)) optout.mutate(); }}>
                {optout.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Ban className="h-3.5 w-3.5" />} Opt out
              </Button>
            </>
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
    queryFn: () => api.get<{ mode: string; count: number; leads: TodayLead[]; send_window?: { ok: boolean; hint: string } }>("/today"),
  });

  const run = useMutation({
    mutationFn: () => api.post<{ count: number }>("/today/run"),
    onSuccess: (d: any) => {
      toast.success(`Discovery started (${d.count} workflow${d.count === 1 ? "" : "s"}). Drafts appear here in a couple of minutes — refresh.`);
      setTimeout(() => {
        qc.invalidateQueries({ queryKey: ["today"] });
        qc.invalidateQueries({ queryKey: ["scraped-data"] });
      }, 4000);
    },
    onError: (e: any) => toast.error(e?.message || "Failed to start"),
  });

  const rescan = useMutation({
    mutationFn: () => api.post("/today/rescan"),
    onSuccess: () => toast.success("Re-scan started — fresh signals & scores land in a minute (also runs weekly on its own)."),
    onError: (e: any) => toast.error(e?.message || "Failed to start re-scan"),
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
        <div className="flex items-center gap-2">
          <Button variant="outline" disabled={rescan.isPending} onClick={() => rescan.mutate()}
                  title="Refresh Places facts on every uncontacted lead: new signals surface, stale ones retire, changed leads re-score. Sends nothing.">
            {rescan.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Re-scan signals
          </Button>
          <Button variant="glow" disabled={run.isPending} onClick={() => run.mutate()}>
            {run.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Run Today&apos;s Discovery
          </Button>
        </div>
      </div>

      {today.data?.send_window && (
        <div className={`rounded-md border px-3 py-2 text-sm flex items-center gap-2 ${
          today.data.send_window.ok
            ? "border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-200"
            : "border-amber-500/30 bg-amber-500/[0.06] text-amber-200"}`}>
          <Clock className="h-4 w-4 shrink-0" />
          {today.data.send_window.hint}
        </div>
      )}

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
