"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, Ban, Check, ChevronDown, Clock, Facebook, Filter, Instagram, Linkedin, Loader2,
  Mail, MapPin, MessageCircle, MessageSquare, Music2, Pencil, Phone, PhoneOff, PlayCircle, RefreshCw, Send, SkipForward, UserSearch, Users, Youtube,
} from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

import { api } from "@/lib/api";
import type { TodayLead } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu, DropdownMenuTrigger, DropdownMenuContent,
  DropdownMenuLabel, DropdownMenuItem, DropdownMenuSeparator,
} from "@/components/ui/dropdown-menu";

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

/** One channel-message block (WhatsApp DM, Arabic DM, comeback, LinkedIn) that can be
 *  edited in place and saved to the draft. Every variant is editable, not just email. */
function VariantBlock({
  companyId, field, value, title, boxCls, labelCls, dir, lang, footer,
}: {
  companyId: string;
  field: "dm" | "dm_ar" | "auto_reply_comeback" | "linkedin_dm";
  value: string; title: string; boxCls: string; labelCls: string;
  dir?: "rtl"; lang?: string; footer?: React.ReactNode;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [text, setText] = useState(value);
  const dirty = text !== value;
  const save = useMutation({
    mutationFn: () => api.patch(`/today/${companyId}/draft`, { [field]: text }),
    onSuccess: () => { toast.success("Saved"); setEditing(false); qc.invalidateQueries({ queryKey: ["today"] }); },
    onError: (e: any) => toast.error(e?.message || "Couldn't save"),
  });
  return (
    <div className={`rounded-md border p-3 space-y-2 ${boxCls}`}>
      <div className="flex items-center justify-between gap-2">
        <div className={`text-[11px] uppercase tracking-wide ${labelCls}`}>{title}</div>
        {!editing ? (
          <button onClick={() => { setText(value); setEditing(true); }}
                  className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground">
            <Pencil className="h-3 w-3" /> Edit
          </button>
        ) : (
          <div className="flex items-center gap-1">
            <Button size="sm" variant="ghost" onClick={() => { setEditing(false); setText(value); }}>Cancel</Button>
            <Button size="sm" variant="default" disabled={!dirty || save.isPending} onClick={() => save.mutate()}>
              {save.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Save"}
            </Button>
          </div>
        )}
      </div>
      {!editing ? (
        <p className="text-sm whitespace-pre-wrap" dir={dir} lang={lang}>{value}</p>
      ) : (
        <textarea value={text} onChange={(e) => setText(e.target.value)} rows={4} dir={dir} lang={lang}
                  className="w-full resize-y rounded-md border border-white/10 bg-background px-2.5 py-2 text-sm outline-none focus:border-brand-400" />
      )}
      {footer}
    </div>
  );
}

function LeadCard({ lead }: { lead: TodayLead }) {
  const qc = useQueryClient();
  const [skipOpen, setSkipOpen] = useState(false);
  const [sentOpen, setSentOpen] = useState(false);
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
  // Which channel they replied on — drives the tone of the drafted response. Default to
  // the most likely channel for this lead, but let the user correct it.
  const replyChannels = [
    lead.wa_link && ["whatsapp", "WhatsApp"],
    lead.ig_dm_link && ["instagram", "Instagram"],
    lead.linkedin_url && ["linkedin", "LinkedIn"],
    lead.to && ["email", "Email"],
  ].filter(Boolean) as [string, string][];
  const [replyChannel, setReplyChannel] = useState<string>(replyChannels[0]?.[0] || "whatsapp");
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

  // Mark sent via the channel you ACTUALLY used, so the Sent page + funnel are honest
  // (the old button hardcoded email). Uses the sent-via endpoint per channel.
  const markSent = useMutation({
    mutationFn: (channel: string) => api.post(`/today/${lead.company_id}/sent-via`, { channel }),
    onSuccess: (_d: any, channel: string) => { toast.success(`Marked sent via ${channel}`); setSentOpen(false); invalidate(); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });
  const skip = useMutation({
    mutationFn: (reason: string) => api.post(`/today/${lead.company_id}/skip`, { reason }),
    onSuccess: () => { toast("Skipped"); invalidate(); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });
  const flagInvalid = useMutation({
    mutationFn: () => api.post(`/today/${lead.company_id}/flag-invalid-whatsapp`),
    onSuccess: () => { toast("Parked — see Invalid Numbers"); invalidate(); },
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
          <VariantBlock companyId={lead.company_id} field="dm" value={lead.dm}
                        title="WhatsApp / DM variant"
                        boxCls="border-emerald-500/20 bg-emerald-500/[0.06]"
                        labelCls="text-emerald-300" />
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
          <VariantBlock companyId={lead.company_id} field="dm_ar" value={lead.dm_ar}
                        title="Arabic DM (العربية)" dir="rtl" lang="ar"
                        boxCls="border-sky-500/20 bg-sky-500/[0.06]"
                        labelCls="text-sky-300" />
        )}

        {lead.linkedin_dm && (
          <VariantBlock companyId={lead.company_id} field="linkedin_dm" value={lead.linkedin_dm}
                        title="LinkedIn message"
                        boxCls="border-blue-500/20 bg-blue-500/[0.06]"
                        labelCls="text-blue-300"
                        footer={
                          <div className="flex flex-wrap items-center gap-2 pt-1">
                            <a href={lead.linkedin_url || "#"} target="_blank" rel="noopener noreferrer"
                               className="inline-flex items-center gap-1.5 rounded-md border border-blue-500/30 bg-blue-500/10 px-2.5 py-1 text-xs text-blue-200 hover:bg-blue-500/20 transition-colors">
                              <Linkedin className="h-3.5 w-3.5" /> Open LinkedIn
                            </a>
                            <Button size="sm" variant="outline" disabled={sentVia.isPending}
                                    onClick={() => sentVia.mutate("linkedin")}>
                              {sentVia.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />} I messaged them
                            </Button>
                          </div>
                        } />
        )}

        {lead.auto_reply_comeback && (
          <VariantBlock companyId={lead.company_id} field="auto_reply_comeback" value={lead.auto_reply_comeback}
                        title="If they auto-reply (send this back)"
                        boxCls="border-amber-500/20 bg-amber-500/[0.06]"
                        labelCls="text-amber-300" />
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button size="sm" variant="outline" disabled={demo.isPending} onClick={() => demo.mutate()}
                  title="Open a WhatsApp-style demo of this clinic's AI receptionist — screenshot it into the chat">
            {demo.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlayCircle className="h-3.5 w-3.5" />} Demo
          </Button>
          <div className="flex-1" />
          {lead.to && (
            <Button size="sm" variant="glow" disabled={sendEmail.isPending}
                    title={`Send this draft now to ${lead.to} from your configured Gmail`}
                    onClick={() => { if (confirm(`Send this email now to ${lead.to}?\n\nThis sends a real email from your configured account. It can't be unsent.`)) sendEmail.mutate(); }}>
              {sendEmail.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Send email
            </Button>
          )}
          {!sentOpen ? (
            <Button size="sm" variant="default" onClick={() => setSentOpen(true)}
                    title="I sent this myself — pick which channel you used so it's tracked correctly.">
              <Check className="h-3.5 w-3.5" /> Mark as sent
            </Button>
          ) : (
            <div className="inline-flex items-center gap-1 rounded-md border border-white/10 bg-background px-1.5 py-1">
              <span className="text-[11px] text-muted-foreground pl-1">Sent via:</span>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-brand-300" disabled={markSent.isPending} onClick={() => markSent.mutate("email")}>
                <Mail className="h-3.5 w-3.5" /> Email
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-emerald-300" disabled={markSent.isPending} onClick={() => markSent.mutate("whatsapp")}>
                <MessageCircle className="h-3.5 w-3.5" /> WhatsApp
              </Button>
              <Button size="sm" variant="ghost" className="h-7 px-2 text-fuchsia-300" disabled={markSent.isPending} onClick={() => markSent.mutate("instagram")}>
                <Instagram className="h-3.5 w-3.5" /> Instagram
              </Button>
              {lead.linkedin_url && (
                <Button size="sm" variant="ghost" className="h-7 px-2 text-blue-300" disabled={markSent.isPending} onClick={() => markSent.mutate("linkedin")}>
                  <Linkedin className="h-3.5 w-3.5" /> LinkedIn
                </Button>
              )}
              {markSent.isPending && <Loader2 className="h-3.5 w-3.5 animate-spin" />}
              <Button size="sm" variant="ghost" className="h-7 px-1.5 text-muted-foreground" onClick={() => setSentOpen(false)}>✕</Button>
            </div>
          )}
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
              <Button size="sm" variant="outline" className="text-amber-400 hover:text-amber-300"
                      disabled={flagInvalid.isPending}
                      title="The WhatsApp number is invalid/unreachable. Park it on the Invalid Numbers page to revisit later."
                      onClick={() => flagInvalid.mutate()}>
                {flagInvalid.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PhoneOff className="h-3.5 w-3.5" />} Bad number
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
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div className="text-[11px] uppercase tracking-wide text-emerald-300">What did they reply?</div>
              {replyChannels.length > 1 && (
                <div className="inline-flex items-center gap-1">
                  <span className="text-[11px] text-muted-foreground">on:</span>
                  {replyChannels.map(([v, label]) => (
                    <button key={v} onClick={() => setReplyChannel(v)}
                            className={`rounded px-1.5 py-0.5 text-[11px] border transition-colors ${
                              replyChannel === v ? "border-emerald-400/50 bg-emerald-500/15 text-emerald-200"
                                                 : "border-white/10 text-muted-foreground hover:text-foreground"}`}>
                      {label}
                    </button>
                  ))}
                </div>
              )}
            </div>
            <textarea value={replyText} onChange={(e) => setReplyText(e.target.value)} rows={3}
                      placeholder="Paste the client's reply here…"
                      className="w-full resize-y rounded-md border border-white/10 bg-background px-2.5 py-2 text-sm outline-none focus:border-emerald-400" />
            <div className="flex items-center gap-2">
              <Button size="sm" variant="default" disabled={!replyText.trim() || logReply.isPending}
                      onClick={() => logReply.mutate(replyChannel)}>
                {logReply.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />} Draft my response
              </Button>
              <span className="text-[11px] text-muted-foreground">Marks the lead as replied.</span>
            </div>
            {suggested && (
              <div className="rounded-md border border-brand-500/25 bg-brand-500/[0.06] p-3 space-y-1">
                <div className="text-[11px] uppercase tracking-wide text-brand-300">Suggested reply (edit before sending)</div>
                <p className="text-sm whitespace-pre-wrap">{suggested}</p>
              </div>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

// Contact-medium filters for the Today list. Each `test` reads the reachable channels
// already on the lead card, so filtering is instant + client-side.
const MEDIA: { key: string; label: string; Icon: any; test: (l: TodayLead) => boolean }[] = [
  { key: "email",     label: "Email",     Icon: Mail,          test: (l) => !!l.to },
  { key: "whatsapp",  label: "WhatsApp",  Icon: MessageCircle, test: (l) => !!l.wa_link },
  { key: "phone",     label: "Phone",     Icon: Phone,         test: (l) => !!l.phone },
  { key: "instagram", label: "Instagram", Icon: Instagram,     test: (l) => !!(l.ig_dm_link || l.ig_handle) },
  { key: "linkedin",  label: "LinkedIn",  Icon: Linkedin,      test: (l) => !!l.linkedin_url },
];

// Which day-bucket a lead falls into (by when it was FOUND/discovered). Undated leads
// (no found_at) sort into "older" so they never vanish from an unfiltered view.
function dayBucket(iso?: string | null): "today" | "yesterday" | "week" | "older" {
  if (!iso) return "older";
  const d = new Date(iso);
  const startOf = (x: Date) => new Date(x.getFullYear(), x.getMonth(), x.getDate()).getTime();
  const days = Math.round((startOf(new Date()) - startOf(d)) / 86400000);
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  if (days <= 7) return "week";
  return "older";
}
const DATE_FILTERS: { key: string; label: string }[] = [
  { key: "today",     label: "Today" },
  { key: "yesterday", label: "Yesterday" },
  { key: "week",      label: "Last 7 days" },
  { key: "older",     label: "Older" },
];
// "week" is inclusive of today+yesterday, so a lead counts for it if it's within 7 days.
function matchesDate(l: TodayLead, key: string): boolean {
  if (key === "all") return true;
  const b = dayBucket(l.found_at);
  if (key === "week") return b === "today" || b === "yesterday" || b === "week";
  return b === key;
}

export default function TodayPage() {
  const qc = useQueryClient();
  const [medium, setMedium] = useState<string>("all");
  const [dateKey, setDateKey] = useState<string>("all");
  const [loc, setLoc] = useState<string>("all");
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

      {(() => {
        const leads = today.data?.leads ?? [];
        if (leads.length === 0) return null;

        // Per-dimension predicates. Each dimension's option counts are computed against
        // the leads already narrowed by the OTHER two, so a count matches what you'll see.
        const activeMedium = MEDIA.find((m) => m.key === medium);
        const mediumOk = (l: TodayLead) => !activeMedium || activeMedium.test(l);
        const dateOk = (l: TodayLead) => matchesDate(l, dateKey);
        const locOf = (l: TodayLead) => l.location || "Unknown";
        const locOk = (l: TodayLead) => loc === "all" || locOf(l) === loc;

        // Distinct locations present in today's leads, most-common first.
        const locCounts = new Map<string, number>();
        for (const l of leads.filter((x) => mediumOk(x) && dateOk(x))) {
          const k = locOf(l);
          locCounts.set(k, (locCounts.get(k) || 0) + 1);
        }
        const allLocs = Array.from(new Set(leads.map(locOf)))
          .sort((a, b) => (locCounts.get(b) || 0) - (locCounts.get(a) || 0) || a.localeCompare(b));

        const forMedium = leads.filter((l) => locOk(l) && dateOk(l));
        const forDate = leads.filter((l) => locOk(l) && mediumOk(l));
        const filtered = leads.filter((l) => locOk(l) && mediumOk(l) && dateOk(l));

        const activeCount = (loc !== "all" ? 1 : 0) + (medium !== "all" ? 1 : 0) + (dateKey !== "all" ? 1 : 0);
        const clearAll = () => { setLoc("all"); setMedium("all"); setDateKey("all"); };

        return (
          <>
            <div className="flex items-center justify-between gap-3 flex-wrap">
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="outline" size="sm" className="gap-1.5">
                    <Filter className="h-3.5 w-3.5" /> Filters
                    {activeCount > 0 && <Badge variant="brand" className="ml-0.5 px-1.5">{activeCount}</Badge>}
                    <ChevronDown className="h-3.5 w-3.5 opacity-70" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start"
                  className="w-64 overflow-y-auto max-h-[min(70vh,var(--radix-dropdown-menu-content-available-height))]">
                  {/* Short, fixed-length sections first (Found + Reachable) so they're
                      always visible; the long, variable Location list scrolls at the end. */}
                  <DropdownMenuLabel className="flex items-center gap-1.5"><Clock className="h-3.5 w-3.5" /> Found</DropdownMenuLabel>
                  <OptionRow label="Any date" count={forDate.length}
                             active={dateKey === "all"} onSelect={() => setDateKey("all")} />
                  {DATE_FILTERS.map((d) => {
                    const n = forDate.filter((l) => matchesDate(l, d.key)).length;
                    return (
                      <OptionRow key={d.key} label={d.label} count={n} disabled={n === 0}
                                 active={dateKey === d.key} onSelect={() => setDateKey(d.key)} />
                    );
                  })}

                  <DropdownMenuSeparator />
                  <DropdownMenuLabel className="flex items-center gap-1.5"><Users className="h-3.5 w-3.5" /> Reachable by</DropdownMenuLabel>
                  <OptionRow label="Any channel" count={forMedium.length}
                             active={medium === "all"} onSelect={() => setMedium("all")} />
                  {MEDIA.map((m) => {
                    const n = forMedium.filter(m.test).length;
                    return (
                      <OptionRow key={m.key} label={m.label} Icon={m.Icon} count={n} disabled={n === 0}
                                 active={medium === m.key} onSelect={() => setMedium(m.key)} />
                    );
                  })}

                  <DropdownMenuSeparator />
                  <DropdownMenuLabel className="flex items-center gap-1.5"><MapPin className="h-3.5 w-3.5" /> Location</DropdownMenuLabel>
                  {/* Location list can be long (many cities) — cap it with its own scroll
                      so it never pushes the sections above off-screen. */}
                  <div className="max-h-40 overflow-y-auto">
                    <OptionRow label="Any location" count={forMedium.length /* == locOk-agnostic base */}
                               active={loc === "all"} onSelect={() => setLoc("all")} />
                    {allLocs.map((L) => (
                      <OptionRow key={L} label={L} count={locCounts.get(L) || 0}
                                 disabled={(locCounts.get(L) || 0) === 0}
                                 active={loc === L} onSelect={() => setLoc(L)} />
                    ))}
                  </div>

                  {activeCount > 0 && (
                    <>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem onSelect={(e) => { e.preventDefault(); clearAll(); }}
                                        className="justify-center text-brand-300 focus:text-brand-200">
                        Clear all filters
                      </DropdownMenuItem>
                    </>
                  )}
                </DropdownMenuContent>
              </DropdownMenu>

              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                {activeCount > 0 && (
                  <div className="flex flex-wrap items-center gap-1">
                    {loc !== "all" && <ActiveTag label={loc} onClear={() => setLoc("all")} />}
                    {medium !== "all" && <ActiveTag label={MEDIA.find((m) => m.key === medium)?.label || medium} onClear={() => setMedium("all")} />}
                    {dateKey !== "all" && <ActiveTag label={DATE_FILTERS.find((d) => d.key === dateKey)?.label || dateKey} onClear={() => setDateKey("all")} />}
                  </div>
                )}
                <span className="tabular-nums whitespace-nowrap">Showing {filtered.length} of {leads.length}</span>
              </div>
            </div>

            <div className="space-y-4">
              {filtered.length === 0 ? (
                <Card><CardContent className="py-8 text-center text-sm text-muted-foreground">
                  No leads match these filters.{" "}
                  <button className="text-brand-300 hover:underline" onClick={clearAll}>Clear filters</button>
                </CardContent></Card>
              ) : (
                filtered.map((l) => <LeadCard key={l.draft_id} lead={l} />)
              )}
            </div>
          </>
        );
      })()}
    </div>
  );
}

// A selectable option inside the Filters dropdown. Keeps the menu open on click so you
// can adjust several filters in one pass; shows a check when active + a live count.
function OptionRow({ label, Icon, count, active, disabled, onSelect }: {
  label: string; Icon?: any; count: number; active: boolean; disabled?: boolean; onSelect: () => void;
}) {
  return (
    <DropdownMenuItem
      disabled={disabled}
      onSelect={(e) => { e.preventDefault(); if (!disabled) onSelect(); }}
      className={`justify-between gap-3 ${active ? "text-brand-200" : ""} ${disabled ? "opacity-40" : ""}`}>
      <span className="inline-flex items-center gap-2 min-w-0">
        <Check className={`h-3.5 w-3.5 shrink-0 ${active ? "opacity-100 text-brand-300" : "opacity-0"}`} />
        {Icon && <Icon className="h-3.5 w-3.5 shrink-0 opacity-70" />}
        <span className="truncate">{label}</span>
      </span>
      <span className="tabular-nums text-xs text-muted-foreground">{count}</span>
    </DropdownMenuItem>
  );
}

// A small removable pill summarising one active filter, shown next to the Filters button.
function ActiveTag({ label, onClear }: { label: string; onClear: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-brand-400/40 bg-brand-500/10 px-2 py-0.5 text-[11px] text-brand-200">
      {label}
      <button onClick={onClear} className="hover:text-white" aria-label={`Clear ${label}`}>✕</button>
    </span>
  );
}
