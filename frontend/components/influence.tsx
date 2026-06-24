"use client";

import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";

export function InfluenceBar({ score }: { score: number }) {
  const tone =
    score >= 80 ? "bg-emerald-400" :
    score >= 60 ? "bg-sky-400" :
    score >= 40 ? "bg-amber-400" : "bg-white/30";
  return (
    <div className="flex items-center gap-2 min-w-[88px]">
      <div className="h-1.5 flex-1 rounded-full bg-white/10 overflow-hidden">
        <div className={cn("h-full rounded-full", tone)} style={{ width: `${Math.max(4, score)}%` }} />
      </div>
      <span className="text-xs tabular-nums text-muted-foreground w-6 text-right">{score}</span>
    </div>
  );
}

const BP_LABEL: Record<string, string> = {
  decision_maker: "Decision maker",
  influencer: "Influencer",
  gatekeeper: "Gatekeeper",
  evaluator: "Evaluator",
  end_user: "End user",
};

export function BuyingPowerBadge({ value }: { value?: string | null }) {
  if (!value) return <span className="text-muted-foreground text-xs">—</span>;
  const variant =
    value === "decision_maker" ? "success" :
    value === "influencer" ? "info" :
    value === "gatekeeper" ? "warn" :
    value === "evaluator" ? "brand" : "default";
  return <Badge variant={variant as any}>{BP_LABEL[value] || value}</Badge>;
}
