"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Building2, DollarSign, ExternalLink, Globe, Layers, Lightbulb, Loader2, MapPin, MessageSquare, Microscope, Rocket, Send, Sparkles, Target, TrendingUp, Users } from "lucide-react";
import { fmtMoney } from "@/lib/utils";
import { toast } from "sonner";

import { api } from "@/lib/api";
import type { AccountResearch, Company, Contact, LeadScore, Page as PageT, Signal } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ScorePill } from "@/components/score-pill";
import { InfluenceBar, BuyingPowerBadge } from "@/components/influence";
import { timeAgo } from "@/lib/utils";

export default function LeadDetailPage() {
  const params = useParams<{ id: string }>();
  const id = params.id;
  const qc = useQueryClient();

  const company = useQuery({
    queryKey: ["company", id],
    queryFn: () => api.get<Company>(`/companies/${id}`),
  });

  const score = useQuery({
    queryKey: ["score", id],
    queryFn: () => api.get<LeadScore>(`/scoring/company/${id}`).catch(() => null),
  });

  const signals = useQuery({
    queryKey: ["signals", id],
    queryFn: () => api.get<PageT<Signal>>(`/signals?company_id=${id}&page_size=50`),
  });

  const contacts = useQuery({
    queryKey: ["contacts", id],
    queryFn: () => api.get<PageT<Contact>>(`/contacts?company_id=${id}`),
  });

  const detect = useMutation({
    mutationFn: () => api.post(`/signals/detect/${id}`),
    onSuccess: () => { toast.success("Signal sweep queued"); qc.invalidateQueries({ queryKey: ["signals", id] }); },
  });
  const findContacts = useMutation({
    mutationFn: () => api.post<Contact[]>(`/contacts/discover/${id}`),
    onSuccess: () => { toast.success("Contacts discovered"); qc.invalidateQueries({ queryKey: ["contacts", id] }); },
  });
  const scoreNow = useMutation({
    mutationFn: () => {
      const icp_id = company.data?.icp_id;
      if (!icp_id) throw new Error("No ICP attached");
      return api.post<LeadScore>(`/scoring/score/${id}/${icp_id}`);
    },
    onSuccess: () => { toast.success("Scored"); qc.invalidateQueries({ queryKey: ["score", id] }); },
    onError: (e: any) => toast.error(e.message),
  });
  const enrich = useMutation({
    mutationFn: () => api.post<Company>(`/companies/${id}/enrich`),
    onSuccess: () => { toast.success("Enriched"); qc.invalidateQueries({ queryKey: ["company", id] }); qc.invalidateQueries({ queryKey: ["signals", id] }); },
    onError: (e: any) => toast.error(e.message),
  });

  if (company.isLoading || !company.data) return <div className="text-sm text-muted-foreground">Loading…</div>;
  const c = company.data;

  return (
    <div className="space-y-6">
      <div className="flex items-start justify-between gap-4 flex-wrap">
        <div className="flex items-center gap-3">
          <div className="flex h-12 w-12 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500/20 to-brand-700/20 border border-brand-500/30">
            <Building2 className="h-5 w-5 text-brand-300" />
          </div>
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">{c.name}</h1>
            <div className="flex items-center gap-3 text-xs text-muted-foreground">
              {c.domain && <a href={c.website || `https://${c.domain}`} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-foreground">
                <Globe className="h-3 w-3" /> {c.domain}
              </a>}
              {c.linkedin_url && <a href={c.linkedin_url} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 hover:text-foreground">
                <ExternalLink className="h-3 w-3" /> LinkedIn
              </a>}
              <Badge variant="brand">{c.pipeline_stage}</Badge>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2 flex-wrap justify-end">
          <Button variant="outline" size="sm" onClick={() => enrich.mutate()} disabled={enrich.isPending}>
            {enrich.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Layers className="h-3.5 w-3.5" />}
            Enrich
          </Button>
          <Button variant="outline" size="sm" onClick={() => detect.mutate()} disabled={detect.isPending}>
            {detect.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Activity className="h-3.5 w-3.5" />}
            Detect signals
          </Button>
          <Button variant="outline" size="sm" onClick={() => findContacts.mutate()} disabled={findContacts.isPending}>
            {findContacts.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Users className="h-3.5 w-3.5" />}
            Find contacts
          </Button>
          <Button variant="glow" size="sm" onClick={() => scoreNow.mutate()} disabled={scoreNow.isPending}>
            {scoreNow.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
            Score
          </Button>
        </div>
      </div>

      {/* Firmographics */}
      <FirmographicsCard c={c} />

      {/* Score summary */}
      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader>
            <CardTitle className="flex items-center justify-between">
              Lead score
              <ScorePill score={score.data?.score} grade={score.data?.grade} />
            </CardTitle>
            <CardDescription>{score.data?.probability != null && `${Math.round(score.data.probability * 100)}% predicted conversion`}</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2">
            {score.data ? (
              <div className="grid grid-cols-2 gap-2 text-xs">
                {[
                  ["Fit", score.data.fit_score],
                  ["Funding", score.data.funding_score],
                  ["Hiring", score.data.hiring_score],
                  ["Growth", score.data.growth_score],
                  ["Tech match", score.data.tech_match_score],
                  ["Email", score.data.email_score],
                  ["Activity", score.data.activity_score],
                ].map(([k, v]) => (
                  <div key={k as string} className="rounded-md border border-white/5 px-3 py-2 bg-white/[0.02]">
                    <div className="text-muted-foreground">{k}</div>
                    <div className="font-medium">{v as number}</div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="text-sm text-muted-foreground">Not scored yet.</div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Why this account, now</CardTitle></CardHeader>
          <CardContent className="space-y-2">
            {score.data?.reasoning?.length ? (
              <ul className="space-y-2 text-sm">
                {score.data.reasoning.map((r, i) => (
                  <li key={i} className="flex gap-2"><span className="text-brand-400">•</span><span>{r}</span></li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">Run a scoring pass to see reasoning.</p>
            )}
            {score.data?.suggested_contact_title && (
              <div className="pt-3 mt-3 border-t border-white/5 text-sm">
                <span className="text-muted-foreground">Suggested contact:</span>{" "}
                <span className="font-medium">{score.data.suggested_contact_title}</span>
              </div>
            )}
            {score.data?.suggested_offer && (
              <div className="text-sm">
                <span className="text-muted-foreground">Suggested offer:</span>{" "}
                <span className="font-medium">{score.data.suggested_offer}</span>
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      {/* Contact channels + saved outreach draft — always visible, mirrors /today */}
      <OutreachPanel companyId={c.id} />

      <Tabs defaultValue="research">
        <TabsList>
          <TabsTrigger value="research">Research</TabsTrigger>
          <TabsTrigger value="signals">Signals ({signals.data?.total ?? 0})</TabsTrigger>
          <TabsTrigger value="contacts">Contacts ({contacts.data?.total ?? 0})</TabsTrigger>
        </TabsList>

        <TabsContent value="research">
          <ResearchPanel companyId={id} />
        </TabsContent>

        <TabsContent value="signals">
          <Card>
            <CardContent className="p-0">
              {signals.data && signals.data.items.length > 0 ? (
                <ul>
                  {signals.data.items.map((s) => (
                    <li key={s.id} className="border-b border-white/5 px-5 py-3 flex items-start gap-3">
                      <Badge variant={
                        s.kind === "funding" ? "success" :
                        s.kind === "hiring" ? "info" :
                        s.kind === "product_launch" ? "brand" :
                        "default"
                      }>{s.kind}</Badge>
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm">{s.label}</div>
                        {s.description && <div className="text-xs text-muted-foreground mt-0.5 line-clamp-2">{s.description}</div>}
                      </div>
                      <div className="text-xs text-muted-foreground">{timeAgo(s.created_at)}</div>
                    </li>
                  ))}
                </ul>
              ) : (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  No signals yet — click <em>Detect signals</em>.
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="contacts">
          <Card>
            <CardContent className="p-0">
              {contacts.data && contacts.data.items.length > 0 ? (
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-xs text-muted-foreground border-b border-white/5">
                      <th className="py-2 px-5">Name</th><th>Title</th><th>Influence</th><th>Buying power</th><th>Email</th><th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {contacts.data.items.map((p) => (
                      <tr key={p.id} className="border-b border-white/5">
                        <td className="py-2.5 px-5 font-medium">{p.name}</td>
                        <td className="text-muted-foreground">{p.title}</td>
                        <td className="pr-4"><InfluenceBar score={p.influence_score} /></td>
                        <td><BuyingPowerBadge value={p.buying_power} /></td>
                        <td className="text-muted-foreground">
                          {p.email || "—"}
                          {p.email_status && (
                            <Badge className="ml-1" variant={
                              p.email_status === "valid" ? "success" :
                              p.email_status === "risky" ? "warn" :
                              p.email_status === "invalid" ? "danger" : "default"
                            }>{p.email_status}</Badge>
                          )}
                        </td>
                        <td className="pr-5 text-right">
                          {p.linkedin_url && <a className="text-xs text-brand-300" href={p.linkedin_url} target="_blank" rel="noreferrer">LinkedIn ↗</a>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <div className="p-8 text-center text-sm text-muted-foreground">
                  No contacts yet — click <em>Find contacts</em>.
                </div>
              )}
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}


function FirmographicsCard({ c }: { c: Company }) {
  const hq = [c.city, c.region, c.country].filter(Boolean).join(", ");
  const cells = [
    { icon: Layers, label: "Industry", value: c.industry || "—" },
    { icon: Users, label: "Employees", value: c.employee_count ? `${c.employee_count}${c.employee_range ? ` (${c.employee_range})` : ""}` : c.employee_range || "—" },
    { icon: DollarSign, label: "Revenue", value: c.revenue_usd ? fmtMoney(c.revenue_usd) : c.revenue_range || "—" },
    { icon: TrendingUp, label: "Funding", value: c.funding_total_usd ? `${fmtMoney(c.funding_total_usd)}${c.last_funding_stage ? ` · ${c.last_funding_stage}` : ""}` : c.last_funding_stage || "—" },
    { icon: MapPin, label: "HQ", value: hq || "—" },
    { icon: Building2, label: "Founded", value: c.founded_year ? String(c.founded_year) : "—" },
  ];
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm">
          Firmographics
          {c.enriched
            ? <Badge variant="success">enriched</Badge>
            : <Badge variant="outline">not enriched</Badge>}
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {cells.map(({ icon: Icon, label, value }) => (
            <div key={label} className="rounded-md border border-white/5 bg-white/[0.02] px-3 py-2">
              <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
                <Icon className="h-3 w-3" /> {label}
              </div>
              <div className="mt-0.5 text-sm font-medium truncate">{value}</div>
            </div>
          ))}
        </div>
        {c.tech_stack && c.tech_stack.length > 0 && (
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1.5">
              Tech stack ({c.tech_stack.length})
            </div>
            <div className="flex flex-wrap gap-1.5">
              {c.tech_stack.map((t) => <Badge key={t} variant="info">{t}</Badge>)}
            </div>
          </div>
        )}
        {c.description && (
          <p className="text-sm text-muted-foreground leading-relaxed border-t border-white/5 pt-3">
            {c.description}
          </p>
        )}
      </CardContent>
    </Card>
  );
}


function ResearchPanel({ companyId }: { companyId: string }) {
  const qc = useQueryClient();
  const existing = useQuery({
    queryKey: ["research", companyId],
    queryFn: () => api.get<AccountResearch>(`/companies/${companyId}/research`).catch(() => null),
  });
  const run = useMutation({
    mutationFn: () => api.post<AccountResearch>(`/companies/${companyId}/research`),
    onSuccess: () => { toast.success("Research complete"); qc.invalidateQueries({ queryKey: ["research", companyId] }); },
    onError: (e: any) => toast.error(e.message || "Research unavailable"),
  });

  const r = run.data || existing.data;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          <span className="flex items-center gap-2"><Microscope className="h-4 w-4 text-brand-400" /> AI Account Research</span>
          <Button size="sm" variant="glow" onClick={() => run.mutate()} disabled={run.isPending}>
            {run.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Microscope className="h-3.5 w-3.5" />}
            {r ? "Re-research" : "Research Account"}
          </Button>
        </CardTitle>
        {r && <CardDescription>Generated {timeAgo(r.created_at)} · confidence {r.confidence}/100 · {r.sources?.length || 0} sources</CardDescription>}
      </CardHeader>
      <CardContent className="space-y-5">
        {!r && !run.isPending && (
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            <Microscope className="h-4 w-4" />
            Run a deep-research pass: website, news, funding, hiring, and tech — synthesized into an actionable brief.
          </div>
        )}
        {run.isPending && (
          <div className="text-sm text-muted-foreground flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Researching across the web…
          </div>
        )}
        {r && (
          <>
            {r.summary && (
              <p className="text-sm leading-relaxed">{r.summary}</p>
            )}
            <ResearchList icon={Lightbulb} title="Pain points" items={r.pain_points} tone="amber" />
            <ResearchList icon={Rocket} title="Current initiatives" items={r.current_initiatives} tone="sky" />
            <ResearchList icon={TrendingUp} title="Growth signals" items={r.growth_signals} tone="emerald" />
            {r.recommended_pitch && (
              <div className="rounded-lg border border-brand-500/20 bg-brand-500/5 p-4">
                <div className="text-[11px] uppercase tracking-wider text-brand-300 mb-1.5 flex items-center gap-1">
                  <Target className="h-3 w-3" /> Recommended pitch
                  {r.suggested_contact_title && <span className="text-muted-foreground normal-case">→ {r.suggested_contact_title}</span>}
                </div>
                <p className="text-sm leading-relaxed">{r.recommended_pitch}</p>
              </div>
            )}
            {r.sources && r.sources.length > 0 && (
              <div className="border-t border-white/5 pt-3">
                <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1.5">Sources</div>
                <div className="flex flex-col gap-1">
                  {r.sources.slice(0, 10).map((s, i) => (
                    <a key={i} href={s.url} target="_blank" rel="noreferrer"
                       className="text-xs text-brand-300 hover:underline truncate">↗ {s.title || s.url}</a>
                  ))}
                </div>
              </div>
            )}
          </>
        )}
      </CardContent>
    </Card>
  );
}

function ResearchList({ icon: Icon, title, items, tone }: {
  icon: any; title: string; items: string[]; tone: "amber" | "sky" | "emerald";
}) {
  if (!items || items.length === 0) return null;
  const color = { amber: "text-amber-400", sky: "text-sky-400", emerald: "text-emerald-400" }[tone];
  return (
    <div>
      <div className={`text-[11px] uppercase tracking-wider text-muted-foreground mb-1.5 flex items-center gap-1`}>
        <Icon className={`h-3 w-3 ${color}`} /> {title}
      </div>
      <ul className="space-y-1">
        {items.map((it, i) => (
          <li key={i} className="flex gap-2 text-sm"><span className={color}>•</span><span>{it}</span></li>
        ))}
      </ul>
    </div>
  );
}


type LeadCard = {
  draft_id: string | null;
  draft_status: string | null;   // 'draft' | 'sent'
  score: number | null; grade: string | null;
  signal: string | null;
  subject: string | null; body: string | null;
  to: string | null; decision_maker: string | null;
  phone: string | null; wa_link: string | null;
  email_mx_ok: boolean | null; spam_flags: string[];
  dm: string | null;
  dm_ar: string | null;
  auto_reply_comeback: string | null;
  socials: Record<string, string>;
};

function copy(text: string, label: string) {
  navigator.clipboard.writeText(text).then(() => toast.success(`${label} copied`));
}

function OutreachPanel({ companyId }: { companyId: string }) {
  const qc = useQueryClient();
  const card = useQuery({
    queryKey: ["lead-card", companyId],
    queryFn: () => api.get<LeadCard>(`/today/company/${companyId}`),
  });
  const redraft = useMutation({
    mutationFn: () => api.post<LeadCard>(`/today/company/${companyId}/draft`),
    onSuccess: () => { toast.success("Draft regenerated"); qc.invalidateQueries({ queryKey: ["lead-card", companyId] }); },
    onError: (e: any) => toast.error(e.message || "Could not draft"),
  });

  const d = card.data;
  const hasDraft = !!(d && d.body);

  return (
    <div className="space-y-4">
      {/* Channels — the same reach info the Today card shows */}
      <Card>
        <CardHeader className="pb-3"><CardTitle className="text-sm">Contact channels</CardTitle></CardHeader>
        <CardContent className="space-y-3 text-sm">
          {d?.signal && (
            <div className="text-xs"><span className="text-muted-foreground">Why it qualified: </span>
              <span className="font-medium text-brand-300">{d.signal}</span></div>
          )}
          <div className="flex flex-wrap gap-2">
            {d?.phone && <Badge variant="outline">☎ {d.phone}</Badge>}
            {d?.wa_link && <a href={d.wa_link} target="_blank" rel="noreferrer">
              <Badge variant="success">WhatsApp ↗</Badge></a>}
            {d?.decision_maker && <Badge variant="brand">{d.decision_maker}</Badge>}
            {d && Object.entries(d.socials || {}).map(([k, url]) => (
              <a key={k} href={url} target="_blank" rel="noreferrer">
                <Badge variant="info">{k} ↗</Badge></a>
            ))}
            {d && !d.phone && !d.wa_link && Object.keys(d.socials || {}).length === 0 && (
              <span className="text-muted-foreground text-xs">No channels found — run Find contacts / Enrich.</span>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Saved outreach draft (parity with /today) */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center justify-between">
            <span className="flex items-center gap-2">
              {d?.draft_status === "sent" ? "Sent message" : "Outreach draft"}
              {d?.draft_status === "sent" && <Badge variant="success">Sent ✓</Badge>}
            </span>
            <Button size="sm" variant={hasDraft ? "outline" : "glow"}
                    onClick={() => redraft.mutate()} disabled={redraft.isPending}
                    title={d?.draft_status === "sent" ? "Generate a fresh draft (e.g. a follow-up) — your sent copy is kept" : undefined}>
              {redraft.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
              {d?.draft_status === "sent" ? "New draft" : hasDraft ? "Re-draft" : "Generate draft"}
            </Button>
          </CardTitle>
          {hasDraft && (
            <CardDescription className="flex flex-wrap items-center gap-2">
              <span>To: {d!.to || <span className="text-amber-400">no email found</span>}</span>
              {d!.to && d!.email_mx_ok === false && <Badge variant="danger">MX fail</Badge>}
              {d!.spam_flags?.length > 0 && <Badge variant="warn">spam: {d!.spam_flags.join(", ")}</Badge>}
            </CardDescription>
          )}
        </CardHeader>
        <CardContent className="space-y-4">
          {card.isLoading && <div className="text-sm text-muted-foreground flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Loading draft…</div>}
          {!card.isLoading && !hasDraft && (
            <div className="text-sm text-muted-foreground flex items-center gap-2"><MessageSquare className="h-4 w-4" />
              No saved draft yet — click <em>Generate draft</em> (uses the same engine as the daily run).
            </div>
          )}
          {hasDraft && (
            <div className="rounded-lg border border-white/5 bg-white/[0.02] p-4 space-y-3">
              <div className="flex items-center justify-between gap-2">
                <div className="text-xs text-muted-foreground">Subject</div>
                <div className="flex gap-1">
                  <Button size="sm" variant="ghost" onClick={() => copy(d!.subject || "", "Subject")}>Copy subject</Button>
                  <Button size="sm" variant="ghost" onClick={() => copy(d!.body || "", "Body")}>Copy body</Button>
                </div>
              </div>
              <div className="font-medium">{d!.subject}</div>
              <div className="text-sm whitespace-pre-wrap leading-relaxed border-t border-white/5 pt-3">{d!.body}</div>
            </div>
          )}
          {d?.dm && (
            <div className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-[11px] uppercase tracking-wider text-emerald-300">WhatsApp / DM variant</div>
                <Button size="sm" variant="ghost" onClick={() => copy(d.dm || "", "DM")}>Copy DM</Button>
              </div>
              <div className="text-sm whitespace-pre-wrap leading-relaxed">{d.dm}</div>
            </div>
          )}
          {d?.dm_ar && (
            <div className="rounded-lg border border-sky-500/20 bg-sky-500/5 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-[11px] uppercase tracking-wider text-sky-300">Arabic DM (العربية)</div>
                <Button size="sm" variant="ghost" onClick={() => copy(d.dm_ar || "", "Arabic DM")}>Copy</Button>
              </div>
              <div className="text-sm whitespace-pre-wrap leading-relaxed" dir="rtl" lang="ar">{d.dm_ar}</div>
            </div>
          )}
          {d?.auto_reply_comeback && (
            <div className="rounded-lg border border-amber-500/20 bg-amber-500/5 p-4 space-y-2">
              <div className="flex items-center justify-between">
                <div className="text-[11px] uppercase tracking-wider text-amber-300">If they auto-reply — send this back</div>
                <Button size="sm" variant="ghost" onClick={() => copy(d.auto_reply_comeback || "", "Comeback")}>Copy</Button>
              </div>
              <div className="text-sm whitespace-pre-wrap leading-relaxed">{d.auto_reply_comeback}</div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
