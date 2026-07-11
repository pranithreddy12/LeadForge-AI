"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Sparkles, Loader2, CheckCircle2, Trash2, RefreshCw } from "lucide-react";
import { motion } from "framer-motion";

import { api } from "@/lib/api";
import type { ICP, Page as PageT } from "@/lib/types";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Textarea } from "@/components/ui/textarea";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

export default function ICPPage() {
  const qc = useQueryClient();
  const [description, setDescription] = useState("");
  const [offering, setOffering] = useState("");

  const list = useQuery({
    queryKey: ["icps"],
    queryFn: () => api.get<PageT<ICP>>("/icps?page_size=20"),
  });

  const gen = useMutation({
    mutationFn: () =>
      api.post<ICP>("/icps/generate", {
        business_description: description,
        target_offering: offering || null,
      }),
    onSuccess: () => {
      toast.success("ICP generated");
      setDescription("");
      setOffering("");
      qc.invalidateQueries({ queryKey: ["icps"] });
    },
    onError: (e: any) => toast.error(e.message || "Failed to generate ICP"),
  });

  const rescore = useMutation({
    mutationFn: () => api.post(`/icps/rescore-leads`),
    onSuccess: () => toast.success("Re-scoring & re-drafting every lead against the active ICP — check /today in a minute."),
    onError: (e: any) => toast.error(e.message || "Could not start re-scoring"),
  });

  const activeIcp = list.data?.items.find((i) => (i as any).is_active);

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between gap-4 flex-wrap">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">AI ICP Generator</h1>
          <p className="text-sm text-muted-foreground">
            Describe your business and we'll build your ideal customer profile.
          </p>
        </div>
        <div className="flex flex-col items-end gap-1">
          <Button
            variant="outline"
            disabled={!activeIcp || rescore.isPending}
            onClick={() => rescore.mutate()}
            title={activeIcp ? `Re-score every lead against "${activeIcp.name}"` : "Activate an ICP first"}
          >
            {rescore.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
            Re-score & re-draft all leads
          </Button>
          {activeIcp && (
            <span className="text-[11px] text-muted-foreground">
              Active: <span className="text-brand-300">{activeIcp.name}</span>
            </span>
          )}
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-400" /> Generate a new ICP
          </CardTitle>
          <CardDescription>
            Example: <em>"We are a QA automation agency serving SaaS Series A–B companies."</em>
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <Textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder="Describe your business…"
            className="min-h-[110px]"
          />
          <Input
            value={offering}
            onChange={(e) => setOffering(e.target.value)}
            placeholder="Service offering (optional)"
          />
          <div className="flex justify-end">
            <Button
              variant="glow"
              disabled={description.trim().length < 10 || gen.isPending}
              onClick={() => gen.mutate()}
            >
              {gen.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
              Generate ICP
            </Button>
          </div>
        </CardContent>
      </Card>

      <div className="grid md:grid-cols-2 gap-4">
        {list.data?.items.map((icp) => (
          <motion.div key={icp.id} initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}>
            <ICPCard icp={icp} />
          </motion.div>
        ))}
        {list.data && list.data.items.length === 0 && (
          <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
            No ICPs yet — generate your first one above.
          </CardContent></Card>
        )}
      </div>
    </div>
  );
}

function ICPCard({ icp }: { icp: ICP }) {
  const qc = useQueryClient();
  const active = (icp as any).is_active;

  const activate = useMutation({
    mutationFn: () => api.post<ICP>(`/icps/${icp.id}/activate`),
    onSuccess: () => {
      toast.success(`"${icp.name}" is now your active ICP`);
      qc.invalidateQueries({ queryKey: ["icps"] });
    },
    onError: (e: any) => toast.error(e.message || "Could not activate"),
  });

  const del = useMutation({
    mutationFn: () => api.delete(`/icps/${icp.id}`),
    onSuccess: () => {
      toast.success(`Deleted "${icp.name}"`);
      qc.invalidateQueries({ queryKey: ["icps"] });
    },
    onError: (e: any) => toast.error(e.message || "Could not delete"),
  });

  return (
    <Card className={active ? "border-brand-500/40" : undefined}>
      <CardHeader>
        <CardTitle className="flex items-center justify-between gap-2">
          <span>{icp.name}</span>
          {active && <Badge variant="brand">Active — used by the daily engine</Badge>}
        </CardTitle>
        <CardDescription>{icp.summary}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-3 text-sm">
        <KV label="Industries" items={icp.industries} />
        <KV label="Countries" items={icp.countries} />
        <KV label="Buyer personas" items={icp.buyer_personas} />
        <KV label="Buying signals" items={icp.buying_signals} variant="success" />
        <KV label="Keywords" items={icp.keywords} variant="info" />
        <div className="flex gap-4 text-xs text-muted-foreground">
          <span>Headcount: {icp.employee_min ?? "—"} – {icp.employee_max ?? "—"}</span>
          {icp.revenue_min_usd && (
            <span>Revenue: ${(icp.revenue_min_usd/1e6).toFixed(0)}M – ${(icp.revenue_max_usd ?? 0)/1e6}M</span>
          )}
        </div>
        <div className="flex items-center gap-2 pt-2 border-t border-white/5">
          {active ? (
            <Button size="sm" variant="ghost" disabled className="text-brand-300">
              <CheckCircle2 className="h-3.5 w-3.5" /> Active
            </Button>
          ) : (
            <Button size="sm" variant="glow" onClick={() => activate.mutate()} disabled={activate.isPending}>
              {activate.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              Use this ICP
            </Button>
          )}
          <Button
            size="sm" variant="ghost"
            className="ml-auto text-red-400 hover:text-red-300"
            disabled={active || del.isPending}
            title={active ? "Activate another ICP before deleting this one" : "Delete this ICP"}
            onClick={() => { if (confirm(`Delete "${icp.name}"? This cannot be undone.`)) del.mutate(); }}
          >
            {del.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            Delete
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function KV({ label, items, variant = "default" }: {
  label: string; items: string[]; variant?: "default" | "info" | "success";
}) {
  if (!items || items.length === 0) return null;
  return (
    <div>
      <div className="text-xs text-muted-foreground mb-1">{label}</div>
      <div className="flex flex-wrap gap-1.5">
        {items.slice(0, 12).map((i) => <Badge key={i} variant={variant}>{i}</Badge>)}
      </div>
    </div>
  );
}
