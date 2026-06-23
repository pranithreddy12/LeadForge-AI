"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { motion } from "framer-motion";
import {
  Activity, ArrowUpRight, Building2, Crosshair, Flame, Sparkles, Target, TrendingUp,
} from "lucide-react";

import { api } from "@/lib/api";
import type { OpportunityCard, OpportunityStats } from "@/lib/types";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScorePill } from "@/components/score-pill";

const SIGNAL_LABEL: Record<string, string> = {
  funding: "Funding", hiring: "Hiring", growth: "Growth",
  product_launch: "Product launch", tech_install: "Tech install",
  leadership_change: "New exec", partnership: "Partnership", news: "News",
  traffic_growth: "Traffic ↑", office_expansion: "Office ↑",
};

export default function OpportunitiesPage() {
  const opps = useQuery({
    queryKey: ["opportunities"],
    queryFn: () => api.get<OpportunityCard[]>("/opportunities?limit=50"),
  });
  const stats = useQuery({
    queryKey: ["opportunities-stats"],
    queryFn: () => api.get<OpportunityStats>("/opportunities/stats"),
  });

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Crosshair className="h-6 w-6 text-brand-400" /> Opportunities
        </h1>
        <p className="text-sm text-muted-foreground">
          Accounts ranked by likelihood to buy — and exactly <em>why</em>.
        </p>
      </div>

      {/* stat strip */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <Stat icon={Target} label="Scored accounts" value={stats.data?.total_scored ?? 0} />
        <Stat icon={Flame} label="Hot (A/A+)" value={stats.data?.hot ?? 0} tone="hot" />
        <Stat icon={TrendingUp} label="Warm (B/C)" value={stats.data?.warm ?? 0} tone="warm" />
        <Stat icon={Activity} label="Avg score" value={stats.data?.avg_score ?? 0} />
      </div>

      {/* opportunity cards */}
      {opps.data && opps.data.length > 0 ? (
        <div className="grid lg:grid-cols-2 gap-4">
          {opps.data.map((o, i) => (
            <motion.div key={o.company_id}
              initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }}
              transition={{ delay: i * 0.03 }}>
              <OppCard o={o} />
            </motion.div>
          ))}
        </div>
      ) : (
        <Card>
          <CardContent className="py-14 text-center">
            <Sparkles className="mx-auto h-8 w-8 text-brand-400/50 mb-3" />
            <p className="text-sm text-muted-foreground">
              No scored opportunities yet. Discover companies, detect signals, then
              <strong> Score</strong> them — they'll appear here ranked by buying intent.
            </p>
            <Link href="/leads" className="mt-3 inline-flex items-center gap-1 text-sm text-brand-300">
              Go to Leads <ArrowUpRight className="h-3.5 w-3.5" />
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Stat({ icon: Icon, label, value, tone }: {
  icon: any; label: string; value: number; tone?: "hot" | "warm";
}) {
  return (
    <Card className="p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className={
          tone === "hot" ? "h-3.5 w-3.5 text-rose-400" :
          tone === "warm" ? "h-3.5 w-3.5 text-amber-400" :
          "h-3.5 w-3.5 text-brand-400"
        } /> {label}
      </div>
      <div className="mt-1.5 text-2xl font-semibold tracking-tight">{value}</div>
    </Card>
  );
}

function OppCard({ o }: { o: OpportunityCard }) {
  const closeRate = Math.round((o.probability ?? 0) * 100);
  return (
    <Card className="overflow-hidden">
      <CardContent className="p-5 space-y-4">
        {/* header */}
        <div className="flex items-start justify-between gap-3">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500/20 to-brand-700/20 border border-brand-500/30 shrink-0">
              <Building2 className="h-5 w-5 text-brand-300" />
            </div>
            <div className="min-w-0">
              <Link href={`/leads/${o.company_id}`} className="font-semibold hover:underline truncate block">
                {o.company_name}
              </Link>
              <div className="text-xs text-muted-foreground truncate">
                {o.industry || o.domain || "—"}
              </div>
            </div>
          </div>
          <div className="text-right shrink-0">
            <ScorePill score={o.score} grade={o.grade} />
            <div className="mt-1 text-[11px] text-muted-foreground">{closeRate}% close</div>
          </div>
        </div>

        {/* signal chips */}
        {o.top_signal_kinds.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {o.top_signal_kinds.map((k) => (
              <Badge key={k} variant={k === "funding" ? "success" : k === "hiring" ? "info" : "brand"}>
                {SIGNAL_LABEL[k] || k}
              </Badge>
            ))}
            <Badge variant="outline">{o.signal_count} signals</Badge>
          </div>
        )}

        {/* WHY NOW — the part buyers pay for */}
        {o.why_now.length > 0 && (
          <div>
            <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1.5">
              Why now
            </div>
            <ul className="space-y-1">
              {o.why_now.slice(0, 4).map((r, i) => (
                <li key={i} className="flex gap-2 text-sm">
                  <span className="text-emerald-400 mt-0.5">✓</span>
                  <span className="text-foreground/90">{r}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* best contact + offer */}
        <div className="grid grid-cols-2 gap-3 pt-1 border-t border-white/5">
          <div>
            <div className="text-[11px] text-muted-foreground">Best contact</div>
            <div className="text-sm font-medium">{o.suggested_contact_title || "—"}</div>
          </div>
          <div>
            <div className="text-[11px] text-muted-foreground">Recommended offer</div>
            <div className="text-sm font-medium line-clamp-2">{o.suggested_offer || "—"}</div>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
