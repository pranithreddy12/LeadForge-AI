"use client";

import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import { Card } from "@/components/ui/card";
import { cn, fmtCount } from "@/lib/utils";

export function KpiCard({
  label,
  value,
  delta,
  format = "count",
}: {
  label: string;
  value: number;
  delta?: number | null;
  format?: "count" | "money" | "percent" | "decimal";
}) {
  const display =
    format === "count" ? fmtCount(value) :
    format === "money" ? "$" + fmtCount(value) :
    format === "percent" ? `${value.toFixed(1)}%` :
    value.toFixed(1);

  const up = (delta ?? 0) >= 0;
  return (
    <Card className="p-5">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-2 flex items-baseline justify-between gap-2">
        <div className="text-2xl font-semibold tracking-tight">{display}</div>
        {delta != null && (
          <div
            className={cn(
              "inline-flex items-center gap-0.5 rounded-md px-1.5 py-0.5 text-xs",
              up ? "text-emerald-300 bg-emerald-500/10" : "text-rose-300 bg-rose-500/10"
            )}
          >
            {up ? <ArrowUpRight className="h-3 w-3" /> : <ArrowDownRight className="h-3 w-3" />}
            {Math.abs(delta).toFixed(1)}%
          </div>
        )}
      </div>
    </Card>
  );
}
