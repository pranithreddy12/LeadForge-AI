"use client";

import {
  Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";

export function ScoreTrendChart({
  data,
}: {
  data: { date: string; avg_score: number; count: number }[];
}) {
  return (
    <ResponsiveContainer width="100%" height={260}>
      <AreaChart data={data} margin={{ left: -10, right: 8, top: 8, bottom: 0 }}>
        <defs>
          <linearGradient id="scoreFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="hsl(230 91% 67%)" stopOpacity={0.55} />
            <stop offset="100%" stopColor="hsl(230 91% 67%)" stopOpacity={0} />
          </linearGradient>
        </defs>
        <CartesianGrid stroke="hsl(220 14% 16%)" strokeDasharray="3 3" />
        <XAxis dataKey="date" stroke="hsl(220 9% 65%)" fontSize={11} tickLine={false} axisLine={false} />
        <YAxis stroke="hsl(220 9% 65%)" fontSize={11} tickLine={false} axisLine={false} domain={[0, 100]} />
        <Tooltip
          contentStyle={{ background: "hsl(224 28% 9%)", border: "1px solid hsl(224 18% 16%)", borderRadius: 8 }}
          labelStyle={{ color: "hsl(220 14% 96%)" }}
        />
        <Area type="monotone" dataKey="avg_score" stroke="hsl(230 91% 67%)" strokeWidth={2} fill="url(#scoreFill)" />
      </AreaChart>
    </ResponsiveContainer>
  );
}
