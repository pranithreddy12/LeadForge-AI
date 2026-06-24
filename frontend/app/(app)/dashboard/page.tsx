"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { Banknote, Crosshair, Flame, UserPlus, Activity, ArrowUpRight } from "lucide-react";
import { api } from "@/lib/api";
import type { DashboardSummary, OpportunityCard } from "@/lib/types";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreTrendChart } from "@/components/charts/score-trend-chart";
import { BreakdownChart } from "@/components/charts/breakdown-chart";
import { GradeDistributionChart } from "@/components/charts/grade-distribution-chart";
import { SignalFeed, type SignalFeedItem } from "@/components/signal-feed";
import { ScorePill } from "@/components/score-pill";
import { Skeleton } from "@/components/ui/skeleton";

type IndustryBreakdown = { industry: string; count: number };
type SourceBreakdown = { source: string; count: number };
type ScoreTrendPoint = { date: string; avg_score: number; count: number };
type GradeBucket = { grade: string; count: number };

export default function DashboardPage() {
  const { data: summary, isLoading } = useQuery({
    queryKey: ["dashboard-summary"],
    queryFn: () => api.get<DashboardSummary>("/dashboard/summary"),
  });
  const { data: industries } = useQuery({
    queryKey: ["dashboard-industries"],
    queryFn: () => api.get<IndustryBreakdown[]>("/dashboard/industries"),
  });
  const { data: sources } = useQuery({
    queryKey: ["dashboard-sources"],
    queryFn: () => api.get<SourceBreakdown[]>("/dashboard/sources"),
  });
  const { data: trend } = useQuery({
    queryKey: ["dashboard-trend"],
    queryFn: () => api.get<ScoreTrendPoint[]>("/dashboard/trend"),
  });
  const { data: distribution } = useQuery({
    queryKey: ["dashboard-distribution"],
    queryFn: () => api.get<GradeBucket[]>("/dashboard/score-distribution"),
  });
  const { data: hot } = useQuery({
    queryKey: ["dashboard-hot"],
    queryFn: () => api.get<OpportunityCard[]>("/opportunities?limit=6"),
  });
  const { data: signalsToday } = useQuery({
    queryKey: ["dashboard-signals-today"],
    queryFn: () => api.get<SignalFeedItem[]>("/dashboard/signals-today?hours=72&limit=8"),
  });
  const { data: funding } = useQuery({
    queryKey: ["dashboard-funding"],
    queryFn: () => api.get<SignalFeedItem[]>("/dashboard/funding-events?limit=6"),
  });
  const { data: execHires } = useQuery({
    queryKey: ["dashboard-exec"],
    queryFn: () => api.get<SignalFeedItem[]>("/dashboard/exec-hires?limit=6"),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
        <p className="text-sm text-muted-foreground">
          What's happening across your pipeline this week.
        </p>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-5 gap-4">
        {isLoading || !summary ? (
          Array.from({ length: 5 }).map((_, i) => (
            <Card key={i} className="p-5"><Skeleton className="h-16" /></Card>
          ))
        ) : (
          <>
            <KpiCard label={summary.leads_found.label} value={summary.leads_found.value} delta={summary.leads_found.delta_pct} />
            <KpiCard label={summary.qualified_leads.label} value={summary.qualified_leads.value} delta={summary.qualified_leads.delta_pct} />
            <KpiCard label={summary.avg_score.label} value={summary.avg_score.value} delta={summary.avg_score.delta_pct} format="decimal" />
            <KpiCard label={summary.conversion_rate.label} value={summary.conversion_rate.value} delta={summary.conversion_rate.delta_pct} format="percent" />
            <KpiCard label={summary.revenue.label} value={summary.revenue.value} delta={summary.revenue.delta_pct} format="money" />
          </>
        )}
      </div>

      {/* command center: hot opportunities + score distribution + signals today */}
      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-1">
          <CardHeader className="flex-row items-center justify-between">
            <CardTitle className="flex items-center gap-2"><Flame className="h-4 w-4 text-rose-400" /> Hot opportunities</CardTitle>
            <Link href="/opportunities" className="text-xs text-brand-300 inline-flex items-center gap-0.5">
              All <ArrowUpRight className="h-3 w-3" />
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {hot && hot.length > 0 ? (
              <ul className="divide-y divide-white/5">
                {hot.slice(0, 6).map((o) => (
                  <li key={o.company_id} className="flex items-center gap-3 px-5 py-2.5">
                    <div className="min-w-0 flex-1">
                      <Link href={`/leads/${o.company_id}`} className="text-sm font-medium truncate hover:underline block">{o.company_name}</Link>
                      <div className="text-[11px] text-muted-foreground truncate">{o.industry || o.domain || "—"}</div>
                    </div>
                    <ScorePill score={o.score} grade={o.grade} />
                  </li>
                ))}
              </ul>
            ) : (
              <div className="px-5 py-8 text-center text-sm text-muted-foreground">No scored accounts yet.</div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-1">
          <CardHeader><CardTitle className="flex items-center gap-2"><Crosshair className="h-4 w-4 text-brand-400" /> Lead score distribution</CardTitle></CardHeader>
          <CardContent>
            {distribution && distribution.some((d) => d.count > 0) ? (
              <GradeDistributionChart data={distribution} />
            ) : (
              <div className="h-[220px] flex items-center justify-center text-sm text-muted-foreground">Score some leads to see the spread.</div>
            )}
          </CardContent>
        </Card>

        <Card className="lg:col-span-1">
          <CardHeader><CardTitle className="flex items-center gap-2"><Activity className="h-4 w-4 text-sky-400" /> Buying signals (72h)</CardTitle></CardHeader>
          <CardContent className="p-0">
            <SignalFeed items={signalsToday || []} emptyHint="No recent signals — run signal detection." />
          </CardContent>
        </Card>
      </div>

      {/* funding events + new exec hires */}
      <div className="grid lg:grid-cols-2 gap-4">
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><Banknote className="h-4 w-4 text-emerald-400" /> Funding events</CardTitle></CardHeader>
          <CardContent className="p-0">
            <SignalFeed items={funding || []} emptyHint="No funding signals detected yet." />
          </CardContent>
        </Card>
        <Card>
          <CardHeader><CardTitle className="flex items-center gap-2"><UserPlus className="h-4 w-4 text-amber-400" /> New executive hires</CardTitle></CardHeader>
          <CardContent className="p-0">
            <SignalFeed items={execHires || []} emptyHint="No leadership-change signals yet." />
          </CardContent>
        </Card>
      </div>

      <div className="grid lg:grid-cols-3 gap-4">
        <Card className="lg:col-span-2">
          <CardHeader><CardTitle>Lead score trend (30d)</CardTitle></CardHeader>
          <CardContent>
            {trend && trend.length > 0 ? (
              <ScoreTrendChart data={trend} />
            ) : (
              <div className="h-[260px] flex items-center justify-center text-sm text-muted-foreground">
                No scored leads yet.
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader><CardTitle>Top industries</CardTitle></CardHeader>
          <CardContent>
            {industries && industries.length > 0 ? (
              <BreakdownChart data={industries} labelKey="industry" />
            ) : (
              <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
                No industry data yet.
              </div>
            )}
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle>Source breakdown</CardTitle></CardHeader>
        <CardContent>
          {sources && sources.length > 0 ? (
            <BreakdownChart data={sources} labelKey="source" />
          ) : (
            <div className="h-[240px] flex items-center justify-center text-sm text-muted-foreground">
              No sources yet — discover your first leads.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
