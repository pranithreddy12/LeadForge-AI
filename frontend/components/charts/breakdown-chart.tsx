"use client";

import { Bar, BarChart, Cell, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";

const palette = [
  "hsl(230 91% 67%)",
  "hsl(190 80% 55%)",
  "hsl(160 70% 55%)",
  "hsl(270 80% 70%)",
  "hsl(330 75% 65%)",
  "hsl(40 90% 60%)",
  "hsl(20 80% 60%)",
  "hsl(210 30% 60%)",
];

export function BreakdownChart({
  data,
  labelKey,
}: {
  data: { count: number; [k: string]: any }[];
  labelKey: string;
}) {
  return (
    <ResponsiveContainer width="100%" height={240}>
      <BarChart data={data} layout="vertical" margin={{ left: 8, right: 16, top: 4, bottom: 0 }}>
        <XAxis type="number" stroke="hsl(220 9% 65%)" fontSize={11} tickLine={false} axisLine={false} />
        <YAxis
          dataKey={labelKey}
          type="category"
          stroke="hsl(220 9% 65%)"
          fontSize={11}
          tickLine={false}
          axisLine={false}
          width={110}
        />
        <Tooltip
          contentStyle={{ background: "hsl(224 28% 9%)", border: "1px solid hsl(224 18% 16%)", borderRadius: 8 }}
        />
        <Bar dataKey="count" radius={6}>
          {data.map((_, i) => (
            <Cell key={i} fill={palette[i % palette.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}
