"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import type { RunLead, Workflow, WorkflowRun } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

function statusVariant(s: string): "brand" | "outline" {
  return s === "success" ? "brand" : "outline";
}

function fmt(ts?: string | null): string {
  if (!ts) return "—";
  const d = new Date(ts);
  return d.toLocaleString(undefined, {
    month: "short", day: "numeric", hour: "2-digit", minute: "2-digit",
  });
}

function funnel(leads: RunLead[]) {
  const discovered = leads.length;
  const qualified = leads.filter((l) => l.qualification_label === "buyer" || l.filter_passed).length;
  const scored65 = leads.filter((l) => (l.score ?? 0) >= 65).length;
  const drafted = leads.filter((l) => !!l.outreach_channel).length;
  const sent = leads.filter((l) => (l.outreach_status || "").includes("sent")).length;
  const replied = leads.filter((l) => l.outreach_status === "replied").length;
  return { discovered, qualified, scored65, drafted, sent, replied };
}

function FunnelBar({ leads }: { leads: RunLead[] }) {
  const f = funnel(leads);
  const steps: Array<[string, number]> = [
    ["discovered", f.discovered], ["qualified", f.qualified],
    ["scored>65", f.scored65], ["drafted", f.drafted],
    ["sent", f.sent], ["replied", f.replied],
  ];
  return (
    <div className="flex flex-wrap items-center gap-1 text-xs">
      {steps.map(([label, n], i) => (
        <span key={label} className="flex items-center gap-1">
          <span className="rounded-md border border-white/10 bg-card/40 px-2 py-0.5">
            <span className="font-semibold tabular-nums">{n}</span>{" "}
            <span className="text-muted-foreground">{label}</span>
          </span>
          {i < steps.length - 1 && <span className="text-muted-foreground">→</span>}
        </span>
      ))}
    </div>
  );
}

function LeadRow({ l }: { l: RunLead }) {
  return (
    <tr className="border-b border-white/5 align-top">
      <td className="py-2 px-3">
        <div className="font-medium">{l.company_name}</div>
        <div className="text-xs text-muted-foreground">{l.city || "—"}</div>
      </td>
      <td className="py-2 px-3">
        {l.score != null
          ? <span className="inline-flex items-center gap-1.5">
              <span className="font-semibold tabular-nums">{l.score}</span>
              {l.grade && <Badge variant="brand">{l.grade}</Badge>}
            </span>
          : <span className="text-muted-foreground">—</span>}
      </td>
      <td className="py-2 px-3 text-xs">
        {l.signals.length ? l.signals.join(", ") : <span className="text-muted-foreground">none</span>}
      </td>
      <td className="py-2 px-3 text-xs">
        {l.outreach_status
          ? <Badge variant={l.outreach_status === "replied" ? "brand" : "outline"}>
              {l.outreach_channel ? `${l.outreach_channel}: ` : ""}{l.outreach_status}
            </Badge>
          : <span className="text-muted-foreground">{l.filter_passed ? "—" : "filtered out"}</span>}
      </td>
      <td className="py-2 px-3 text-xs text-muted-foreground max-w-[280px]">
        {l.suppression_reason || "—"}
      </td>
    </tr>
  );
}

function RunCard({ run }: { run: WorkflowRun }) {
  const [open, setOpen] = useState(false);
  const leads = run.run_leads || [];
  return (
    <div className="rounded-lg border border-white/5 bg-card/30">
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 px-4 py-3 text-left"
      >
        {open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
        <span className="text-sm text-muted-foreground w-32 shrink-0">{fmt(run.finished_at || run.created_at)}</span>
        <Badge variant={statusVariant(run.status)}>{run.status}</Badge>
        <div className="flex-1"><FunnelBar leads={leads} /></div>
      </button>
      {open && (
        <div className="px-4 pb-4">
          {leads.length === 0 ? (
            <p className="text-sm text-muted-foreground py-3">
              No lead-level detail captured for this run.
            </p>
          ) : (
            <div className="overflow-x-auto rounded-md border border-white/5">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-muted-foreground border-b border-white/5">
                    <th className="py-2 px-3">Business</th>
                    <th className="py-2 px-3">Score</th>
                    <th className="py-2 px-3">Signals</th>
                    <th className="py-2 px-3">Outreach</th>
                    <th className="py-2 px-3">Suppression</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((l) => <LeadRow key={l.company_id} l={l} />)}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function WorkflowRuns({ workflow }: { workflow: Workflow }) {
  const runs = useQuery({
    queryKey: ["runs", workflow.id],
    queryFn: () => api.get<WorkflowRun[]>(`/workflows/${workflow.id}/runs?limit=25`),
  });
  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">{workflow.name}</CardTitle>
      </CardHeader>
      <CardContent className="space-y-2">
        {runs.isLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
        {runs.data?.length === 0 && (
          <p className="text-sm text-muted-foreground">No runs yet.</p>
        )}
        {runs.data?.map((r) => <RunCard key={r.id} run={r} />)}
      </CardContent>
    </Card>
  );
}

export default function RunsPage() {
  const workflows = useQuery({
    queryKey: ["workflows"],
    queryFn: () => api.get<Workflow[]>("/workflows"),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Runs</h1>
        <p className="text-sm text-muted-foreground">
          Audit every workflow run — funnel counts and lead-level detail.
        </p>
      </div>
      {workflows.isLoading && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {workflows.data?.length === 0 && (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
          No workflows yet.
        </CardContent></Card>
      )}
      {workflows.data?.map((wf) => <WorkflowRuns key={wf.id} workflow={wf} />)}
    </div>
  );
}
