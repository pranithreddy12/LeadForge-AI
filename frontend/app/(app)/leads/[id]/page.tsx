"use client";

import { useParams } from "next/navigation";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Activity, Building2, ExternalLink, Globe, Loader2, MessageSquare, Send, Sparkles, Users } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import type { Company, Contact, LeadScore, Page as PageT, Signal } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { ScorePill } from "@/components/score-pill";
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
        <div className="flex items-center gap-2">
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

      <Tabs defaultValue="signals">
        <TabsList>
          <TabsTrigger value="signals">Signals ({signals.data?.total ?? 0})</TabsTrigger>
          <TabsTrigger value="contacts">Contacts ({contacts.data?.total ?? 0})</TabsTrigger>
          <TabsTrigger value="outreach">Outreach</TabsTrigger>
        </TabsList>

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
                      <th className="py-2 px-5">Name</th><th>Title</th><th>Email</th><th>Status</th><th></th>
                    </tr>
                  </thead>
                  <tbody>
                    {contacts.data.items.map((p) => (
                      <tr key={p.id} className="border-b border-white/5">
                        <td className="py-2.5 px-5 font-medium">{p.name}</td>
                        <td className="text-muted-foreground">{p.title}</td>
                        <td className="text-muted-foreground">{p.email || "—"}</td>
                        <td>
                          {p.email_status && (
                            <Badge variant={
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

        <TabsContent value="outreach">
          <OutreachPanel companyId={c.id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}


function OutreachPanel({ companyId }: { companyId: string }) {
  type V = { subject: string; body: string };
  const m = useMutation({
    mutationFn: () => api.post<{ variants: V[] }>(`/campaigns/outreach`, {
      company_id: companyId, channel: "email", tone: "concise", follow_up: 0,
    }),
    onError: (e: any) => toast.error(e.message),
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center justify-between">
          AI outreach drafts
          <Button size="sm" variant="glow" onClick={() => m.mutate()} disabled={m.isPending}>
            {m.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Send className="h-3.5 w-3.5" />}
            Generate
          </Button>
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {!m.data && !m.isPending && (
          <div className="text-sm text-muted-foreground flex items-center gap-2"><MessageSquare className="h-4 w-4" />
            Generate two AI-personalized email drafts grounded in detected signals.
          </div>
        )}
        {m.data?.variants?.map((v, i) => (
          <div key={i} className="rounded-lg border border-white/5 bg-white/[0.02] p-4">
            <div className="text-xs text-muted-foreground mb-1">Variant {i + 1} — Subject</div>
            <div className="font-medium mb-3">{v.subject}</div>
            <div className="text-sm whitespace-pre-wrap leading-relaxed">{v.body}</div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
