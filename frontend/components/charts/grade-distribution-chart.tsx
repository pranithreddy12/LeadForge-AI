"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const GRADE_COLOR: Record<string, string> = {
  "A+": "hsl(152 70% 50%)",
  "A": "hsl(152 60% 45%)",
  "B": "hsl(199 80% 55%)",
  "C": "hsl(40 90% 58%)",
  "D": "hsl(25 85% 58%)",
  "F": "hsl(350 75% 60%)",
};

export function GradeDistributionChart({ data }: { data: { grade: string; count: number }[] }) {
  return (
    <ResponsiveContainer width="100%" height={220}>
      <BarChart data={data} margin={{ left: -16, right: 8, top: 8, bottom: 0 }}>
        <XAxis dataKey="grade" stroke="hsl(220 9% 65%)" fontSize={12} tickLine={false} axisLine={false} />
        <YAxis stroke="hsl(220 9% 65%)" fontSize={11} tickLine={false} axisLine={false} allowDecimals={false} />
        <Tooltip
          cursor={{ fill: "hsl(220 14% 16% / 0.4)" }}
          contentStyle={{ background: "hsl(224 28% 9%)", border: "1px solid hsl(224 18% 16%)", borderRadius: 8 }}
        />
        <Bar dataKey="count" radius={6}>
          {data.map((d) => <Cell key={d.grade} fill={GRADE_COLOR[d.grade] || "hsl(230 91% 67%)"} />)}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
