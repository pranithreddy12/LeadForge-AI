"use client";

import { useQuery } from "@tanstack/react-query";
import { api } from "@/lib/api";
import type { DashboardSummary } from "@/lib/types";
import { KpiCard } from "@/components/kpi-card";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { ScoreTrendChart } from "@/components/charts/score-trend-chart";
import { BreakdownChart } from "@/components/charts/breakdown-chart";
import { Skeleton } from "@/components/ui/skeleton";

type IndustryBreakdown = { industry: string; count: number };
type SourceBreakdown = { source: string; count: number };
type ScoreTrendPoint = { date: string; avg_score: number; count: number };

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
