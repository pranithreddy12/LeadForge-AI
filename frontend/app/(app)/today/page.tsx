"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, Ban, Check, Clock, Copy, Facebook, Instagram, Linkedin, Loader2,
  MessageCircle, MessageSquare, Music2, Pencil, PlayCircle, RefreshCw, Send, SkipForward, UserSearch, Youtube,
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

/** Copy silently — used when opening an IG DM so the message is already on the
 *  clipboard when the chat window appears (Instagram can't be pre-filled by URL). */
function copyText(text: string) {
  navigator.clipboard.writeText(text).then(
    () => toast.success("DM copied — paste it in the chat"),
    () => toast.error("Couldn't copy — copy the DM manually"),
  );
}

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
  const [editing, setEditing] = useState(false);
  const [subj, setSubj] = useState(lead.subject);
  const [body, setBody] = useState(lead.body);
  const dirty = subj !== lead.subject || body !== lead.body;
  const invalidate = () => qc.invalidateQueries({ queryKey: ["today"] });

  const saveEdit = useMutation({
    mutationFn: () => api.patch(`/today/${lead.company_id}/draft`, { subject: subj, body }),
    onSuccess: () => { toast.success("Draft saved"); setEditing(false); invalidate(); },
    onError: (e: any) => toast.error(e?.message || "Couldn't save"),
  });
  const demo = useMutation({
    mutationFn: () => api.get<{ html: string }>(`/today/${lead.company_id}/demo`),
    onSuccess: (d: any) => {
      // Open the generated demo page in a new tab (blob) — screenshot it into WhatsApp/IG.
      const url = URL.createObjectURL(new Blob([d.html], { type: "text/html" }));
      window.open(url, "_blank", "noopener,noreferrer");
      setTimeout(() => URL.revokeObjectURL(url), 60000);
    },
    onError: (e: any) => toast.error(e?.message || "Couldn't build demo"),
  });
  const sentVia = useMutation({
    mutationFn: (channel: string) => api.post(`/today/${lead.company_id}/sent-via`, { channel }),
    onSuccess: (_d: any, channel: string) => { toast.success(`Logged — ${channel} outreach sent`); invalidate(); },
    onError: (e: any) => toast.error(e?.message || "Couldn't log"),
  });
  const [replyOpen, setReplyOpen] = useState(false);
  const [replyText, setReplyText] = useState("");
  const [suggested, setSuggested] = useState<string | null>(null);
  const logReply = useMutation({
    mutationFn: (channel: string) =>
      api.post<{ suggested_response: string | null; detail?: string }>(
        `/today/${lead.company_id}/log-reply`, { their_message: replyText, channel }),
    onSuccess: (d: any) => {
      setSuggested(d.suggested_response || null);
      toast.success(d.suggested_response ? "Reply logged — AI drafted your response" : (d.detail || "Reply logged"));
    },
    onError: (e: any) => toast.error(e?.message || "Failed to log reply"),
  });
  const findOwner = useMutation({
    mutationFn: () => api.post<{ found: boolean; email?: string; detail?: string }>(`/today/${lead.company_id}/find-owner-email`),
    onSuccess: (d: any) => {
      if (d.found) { toast.success(`Found owner email: ${d.email}`); invalidate(); }
      else toast(d.detail || "No owner email found", { icon: "ℹ️" });
    },
    onError: (e: any) => toast.error(e?.message || "Lookup failed"),
  });

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
    // Persist any pending edits first so we always send exactly what's on screen.
    mutationFn: async () => {
      if (dirty) await api.patch(`/today/${lead.company_id}/draft`, { subject: subj, body });
      return api.post<{ sent: boolean; to?: string; reason?: string; detail?: string }>(`/today/${lead.company_id}/send-email`);
    },
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
          <div className="flex items-center justify-between">
            <div className="text-[11px] uppercase tracking-wide text-muted-foreground">Drafted email {(lead as any).edited && <span className="text-brand-300">· edited</span>}</div>
            {!editing ? (
              <button onClick={() => { setSubj(lead.subject); setBody(lead.body); setEditing(true); }}
                      className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
                <Pencil className="h-3 w-3" /> Edit
              </button>
            ) : (
              <div className="flex items-center gap-1">
                <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setSubj(lead.subject); setBody(lead.body); }}>Cancel</Button>
                <Button size="sm" variant="default" disabled={!dirty || saveEdit.isPending} onClick={() => saveEdit.mutate()}>
                  {saveEdit.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
                </Button>
              </div>
            )}
          </div>
          <div className="flex items-center justify-between gap-2">
            <div className="text-sm">
              <span className="text-muted-foreground">To:</span> {lead.to || <span className="text-amber-500">no email found</span>}
              {lead.to && /^(info|contact|hello|admin|reception|book|appointment|enquiry|enquiries|support|office|reservations|customersupport|wecare)@/i.test(lead.to) && (
                <span className="ml-1.5 text-[11px] text-amber-500">· front-desk inbox</span>
              )}
            </div>
            {lead.domain && (!lead.to || /^(info|contact|hello|admin|reception|book|appointment|enquiry|enquiries|support|office|reservations|customersupport|wecare)@/i.test(lead.to || "")) && (
              <button onClick={() => findOwner.mutate()} disabled={findOwner.isPending}
                      title="Look up the owner's personal email from their name (verified — never a guess)"
                      className="inline-flex items-center gap-1 whitespace-nowrap text-xs text-brand-300 hover:text-brand-200">
                {findOwner.isPending ? <Loader2 className="h-3 w-3 animate-spin" /> : <UserSearch className="h-3 w-3" />} Find owner email
              </button>
            )}
          </div>
          {!editing ? (
            <>
              <div className="text-sm"><span className="text-muted-foreground">Subject:</span> {lead.subject}</div>
              <p className="text-sm whitespace-pre-wrap pt-1 border-t border-white/5">{lead.body}</p>
            </>
          ) : (
            <div className="space-y-2 pt-1">
              <input value={subj} onChange={(e) => setSubj(e.target.value)} placeholder="Subject"
                     className="w-full rounded-md border border-white/10 bg-background px-2.5 py-1.5 text-sm outline-none focus:border-brand-400" />
              <textarea value={body} onChange={(e) => setBody(e.target.value)} rows={7}
                        className="w-full resize-y rounded-md border border-white/10 bg-background px-2.5 py-2 text-sm leading-relaxed outline-none focus:border-brand-400" />
              <p className="text-[11px] text-muted-foreground">Edits are saved to this draft. “Send email” always sends your latest version.</p>
            </div>
          )}
        </div>

        {lead.dm && (
          <div className="rounded-md border border-emerald-500/20 bg-emerald-500/[0.06] p-3 space-y-1">
            <div className="text-[11px] uppercase tracking-wide text-emerald-300">WhatsApp / DM variant</div>
            <p className="text-sm whitespace-pre-wrap">{lead.dm}</p>
          </div>
        )}

        {lead.ig_dm_link && (
          <div className="rounded-md border border-fuchsia-500/20 bg-fuchsia-500/[0.06] p-3 space-y-2">
            <div className="flex items-center justify-between gap-2">
              <div className="text-[11px] uppercase tracking-wide text-fuchsia-300">
                Instagram · @{lead.ig_handle}
              </div>
              <a href={lead.ig_profile || "#"} target="_blank" rel="noopener noreferrer"
                 className="text-[11px] text-muted-foreground hover:text-foreground">View profile ↗</a>
            </div>
            <p className="text-[11px] text-muted-foreground">
              Owners read IG themselves. Check the profile is active, then DM the text above — never a cold blast.
            </p>
            <div className="flex flex-wrap items-center gap-2">
              <a href={lead.ig_dm_link} target="_blank" rel="noopener noreferrer"
                 onClick={() => { if (lead.dm) copyText(lead.dm); }}
                 className="inline-flex items-center gap-1.5 rounded-md border border-fuchsia-500/30 bg-fuchsia-500/10 px-2.5 py-1 text-xs text-fuchsia-200 hover:bg-fuchsia-500/20 transition-colors">
                <Instagram className="h-3.5 w-3.5" /> Open DM {lead.dm && "(copies text)"}
              </a>
              <Button size="sm" variant="outline" disabled={sentVia.isPending}
                      onClick={() => sentVia.mutate("instagram")}>
                {sentVia.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} I DM'd them
              </Button>
            </div>
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
          <Button size="sm" variant="outline" disabled={demo.isPending} onClick={() => demo.mutate()}
                  title="Open a WhatsApp-style demo of this clinic's AI receptionist — screenshot it into the chat">
            {demo.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlayCircle className="h-3.5 w-3.5" />} Demo
          </Button>
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
              <Button size="sm" variant="outline" className="text-emerald-300 hover:text-emerald-200"
                      onClick={() => { setReplyOpen((v) => !v); setSuggested(null); }}
                      title="They replied to your DM/email — paste it and get an AI-drafted response.">
                <MessageSquare className="h-3.5 w-3.5" /> They replied
              </Button>
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

        {replyOpen && (
          <div className="rounded-md border border-emerald-500/25 bg-emerald-500/[0.05] p-3 space-y-2">
            <div className="text-[11px] uppercase tracking-wide text-emerald-300">What did they reply?</div>
            <textarea value={replyText} onChange={(e) => setReplyText(e.target.value)} rows={3}
                      placeholder="Paste the client's reply here…"
                      className="w-full resize-y rounded-md border border-white/10 bg-background px-2.5 py-2 text-sm outline-none focus:border-emerald-400" />
            <div className="flex items-center gap-2">
              <Button size="sm" variant="default" disabled={!replyText.trim() || logReply.isPending}
                      onClick={() => logReply.mutate(lead.ig_dm_link ? "instagram" : lead.wa_link ? "whatsapp" : "email")}>
                {logReply.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Draft my response
              </Button>
              <span className="text-[11px] text-muted-foreground">Marks the lead as replied.</span>
            </div>
            {suggested && (
              <div className="rounded-md border border-brand-500/25 bg-brand-500/[0.06] p-3 space-y-1">
                <div className="flex items-center justify-between">
                  <div className="text-[11px] uppercase tracking-wide text-brand-300">Suggested reply (edit before sending)</div>
                  <CopyBtn text={suggested} label="Copy reply" />
                </div>
                <p className="text-sm whitespace-pre-wrap">{suggested}</p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function TodayPage() {
  const qc = useQueryClient();
  const today = useQuery({
    queryKey: ["today"],
    queryFn: () => api.get<{
      mode: string; count: number; leads: TodayLead[];
      send_window?: { ok: boolean; hint: string };
      sending_health?: {
        status: "ok" | "warning" | "critical";
        bounce_rate: number | null; reply_rate: number | null;
        attempted_30d: number; sent_today: number; daily_cap: number;
        from_address: string | null; personal_account: boolean;
        issues: { level: string; text: string }[];
      };
    }>("/today"),
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
  const enrichOwners = useMutation({
    mutationFn: () => api.post<{ found: number; scanned: number; needs_key: boolean; detail: string }>("/today/enrich-owner-emails"),
    onSuccess: (d: any) => {
      if (d.needs_key) toast(d.detail, { icon: "🔑", duration: 6000 });
      else { toast.success(d.detail); qc.invalidateQueries({ queryKey: ["today"] }); }
    },
    onError: (e: any) => toast.error(e?.message || "Failed"),
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
          <Button variant="outline" disabled={enrichOwners.isPending} onClick={() => enrichOwners.mutate()}
                  title="Find decision-maker emails for every qualified lead from their scraped owner name (needs a Hunter/NeverBounce key; verified only, never a guess).">
            {enrichOwners.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <UserSearch className="h-4 w-4" />}
            Find decision-maker emails
          </Button>
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

      {today.data?.sending_health && (() => {
        const h = today.data.sending_health!;
        const tone = h.status === "critical"
          ? "border-red-500/30 bg-red-500/[0.06] text-red-200"
          : h.status === "warning"
          ? "border-amber-500/30 bg-amber-500/[0.06] text-amber-200"
          : "border-emerald-500/30 bg-emerald-500/[0.06] text-emerald-200";
        return (
          <div className={`rounded-md border px-3 py-2 text-sm ${tone}`}>
            <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
              <span className="inline-flex items-center gap-1.5 font-medium">
                <Activity className="h-4 w-4 shrink-0" /> Sending health
              </span>
              <span className="tabular-nums">
                Bounce: {h.bounce_rate == null ? "—" : `${h.bounce_rate}%`}
                <span className="text-muted-foreground"> (of {h.attempted_30d} sent, 30d)</span>
              </span>
              <span className="tabular-nums">
                Replies: {h.reply_rate == null ? "—" : `${h.reply_rate}%`}
              </span>
              <span className="tabular-nums">
                Today: {h.sent_today}/{h.daily_cap}
              </span>
              {h.from_address && (
                <span className="text-muted-foreground">from {h.from_address}</span>
              )}
            </div>
            {h.issues.length > 0 && (
              <ul className="mt-1.5 space-y-0.5">
                {h.issues.map((i, n) => (
                  <li key={n} className="text-xs opacity-90">• {i.text}</li>
                ))}
              </ul>
            )}
          </div>
        );
      })()}

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
