"use client";
import { cn } from "@/lib/utils";

export function ScorePill({ score, grade }: { score?: number | null; grade?: string | null }) {
  if (score == null || !grade) return <span className="text-muted-foreground text-xs">—</span>;
  const cls =
    grade === "A+" ? "grade-A\\+" :
    grade === "A" ? "grade-A" :
    grade === "B" ? "grade-B" :
    grade === "C" ? "grade-C" :
    grade === "D" ? "grade-D" : "grade-F";
  return (
    <span className={cn("grade-pill", cls)}>
      {grade} · {score}
    </span>
  );
}
