"use client";

import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { Building2, Filter, Loader2, RefreshCw, Search } from "lucide-react";
import { toast } from "sonner";
import Link from "next/link";

import { api } from "@/lib/api";
import type { Company, ICP, Page as PageT } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

const STAGES = ["new", "qualified", "contacted", "replied", "meeting", "proposal", "won", "lost"];

export default function LeadsPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [stage, setStage] = useState<string | null>(null);
  const [icpId, setIcpId] = useState<string | null>(null);

  const icps = useQuery({
    queryKey: ["icps", "all"],
    queryFn: () => api.get<PageT<ICP>>("/icps?page_size=50"),
  });

  const companies = useQuery({
    queryKey: ["companies", { q, stage, icpId }],
    queryFn: () => api.get<PageT<Company>>(
      `/companies?page_size=50${q ? `&q=${encodeURIComponent(q)}` : ""}` +
      `${stage ? `&pipeline_stage=${stage}` : ""}${icpId ? `&icp_id=${icpId}` : ""}`,
    ),
  });

  const discover = useMutation({
    mutationFn: (icp_id: string) => api.post("/companies/discover", { icp_id, limit: 25 }),
    onSuccess: () => {
      toast.success("Discovery queued");
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (e: any) => toast.error(e.message),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between gap-3 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Leads</h1>
          <p className="text-sm text-muted-foreground">All companies in your workspace.</p>
        </div>
        <div className="flex items-center gap-2">
          <select
            className="h-9 rounded-md bg-card/40 border border-input px-3 text-sm"
            value={icpId ?? ""}
            onChange={(e) => setIcpId(e.target.value || null)}
          >
            <option value="">Choose ICP…</option>
            {icps.data?.items.map((i) => (
              <option key={i.id} value={i.id}>{i.name}</option>
            ))}
          </select>
          <Button
            variant="glow"
            disabled={!icpId || discover.isPending}
            onClick={() => icpId && discover.mutate(icpId)}
          >
            {discover.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Discover
          </Button>
        </div>
      </div>

      <Card className="p-3">
        <div className="flex items-center gap-2">
          <div className="relative flex-1">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search company or domain…"
              className="pl-9 h-9 bg-card/40"
            />
          </div>
          <div className="flex items-center gap-2 overflow-x-auto">
            <Filter className="h-4 w-4 text-muted-foreground" />
            {STAGES.map((s) => (
              <button
                key={s}
                onClick={() => setStage(stage === s ? null : s)}
                className={
                  "rounded-md px-2.5 py-1 text-xs border transition-colors " +
                  (stage === s
                    ? "border-brand-500/40 bg-brand-500/15 text-brand-200"
                    : "border-white/10 bg-card/30 text-muted-foreground hover:text-foreground")
                }
              >
                {s}
              </button>
            ))}
          </div>
        </div>
      </Card>

      <Card>
        <CardHeader><CardTitle>{companies.data?.total ?? 0} companies</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-white/5">
                  <th className="py-2 px-4">Company</th>
                  <th className="py-2 px-4">Industry</th>
                  <th className="py-2 px-4">Employees</th>
                  <th className="py-2 px-4">Country</th>
                  <th className="py-2 px-4">Stage</th>
                  <th className="py-2 px-4">Source</th>
                </tr>
              </thead>
              <tbody>
                {companies.data?.items.map((c) => (
                  <tr key={c.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                    <td className="py-2.5 px-4">
                      <Link href={`/leads/${c.id}`} className="flex items-center gap-2 hover:underline">
                        <div className="flex h-7 w-7 items-center justify-center rounded-md bg-white/5 text-muted-foreground">
                          <Building2 className="h-3.5 w-3.5" />
                        </div>
                        <div>
                          <div className="font-medium">{c.name}</div>
                          <div className="text-xs text-muted-foreground">{c.domain}</div>
                        </div>
                      </Link>
                    </td>
                    <td className="py-2.5 px-4 text-muted-foreground">{c.industry || "—"}</td>
                    <td className="py-2.5 px-4 text-muted-foreground">{c.employee_count ?? "—"}</td>
                    <td className="py-2.5 px-4 text-muted-foreground">{c.country || "—"}</td>
                    <td className="py-2.5 px-4"><Badge variant="brand">{c.pipeline_stage}</Badge></td>
                    <td className="py-2.5 px-4 text-muted-foreground">{c.source || "manual"}</td>
                  </tr>
                ))}
                {companies.data?.items.length === 0 && (
                  <tr><td colSpan={6} className="py-10 text-center text-sm text-muted-foreground">
                    No companies yet. Choose an ICP and click <em>Discover</em>.
                  </td></tr>
                )}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
