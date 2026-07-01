"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import type { ManualLogItem } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";

type LogResp = {
  summary: { reviewed: number; sent: number; skipped: number; replied: number; days: number };
  items: ManualLogItem[];
};

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card><CardContent className="py-4 text-center">
      <div className="text-2xl font-semibold tabular-nums">{value}</div>
      <div className="text-xs text-muted-foreground">{label}</div>
    </CardContent></Card>
  );
}

function fmt(ts?: string | null) {
  if (!ts) return "—";
  return new Date(ts).toLocaleString(undefined, { month: "short", day: "numeric", hour: "2-digit", minute: "2-digit" });
}

export default function LogPage() {
  const qc = useQueryClient();
  const log = useQuery({ queryKey: ["log"], queryFn: () => api.get<LogResp>("/log?days=7") });

  const toggleReplied = useMutation({
    mutationFn: ({ id, replied }: { id: string; replied: boolean }) => api.patch(`/log/${id}`, { replied }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["log"] }); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });

  const s = log.data?.summary;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Outreach Log</h1>
        <p className="text-sm text-muted-foreground">Your manual-send sprint, last {s?.days ?? 7} days.</p>
      </div>

      {log.isLoading && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}

      {s && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          <Stat label="Reviewed" value={s.reviewed} />
          <Stat label="Sent" value={s.sent} />
          <Stat label="Skipped" value={s.skipped} />
          <Stat label="Replied" value={s.replied} />
        </div>
      )}

      <Card>
        <CardHeader><CardTitle>History</CardTitle></CardHeader>
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-white/5">
                  <th className="py-2 px-4">When</th>
                  <th className="py-2 px-4">Company</th>
                  <th className="py-2 px-4">Channel</th>
                  <th className="py-2 px-4">Action</th>
                  <th className="py-2 px-4">Replied?</th>
                </tr>
              </thead>
              <tbody>
                {log.data?.items.map((r) => (
                  <tr key={r.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                    <td className="py-2.5 px-4 text-muted-foreground">{fmt(r.at)}</td>
                    <td className="py-2.5 px-4 font-medium">{r.company_name}</td>
                    <td className="py-2.5 px-4">{r.channel}</td>
                    <td className="py-2.5 px-4">
                      {r.action === "sent"
                        ? <Badge variant="brand">sent</Badge>
                        : <Badge variant="outline">skipped{r.skip_reason ? `: ${r.skip_reason}` : ""}</Badge>}
                    </td>
                    <td className="py-2.5 px-4">
                      {r.action === "sent" ? (
                        <label className="inline-flex items-center gap-2 cursor-pointer">
                          <input type="checkbox" checked={r.replied}
                                 onChange={(e) => toggleReplied.mutate({ id: r.id, replied: e.target.checked })} />
                          {r.replied ? <Badge variant="brand">replied</Badge> : <span className="text-muted-foreground text-xs">mark</span>}
                        </label>
                      ) : <span className="text-muted-foreground">—</span>}
                    </td>
                  </tr>
                ))}
                {log.data?.items.length === 0 && (
                  <tr><td colSpan={5} className="py-10 text-center text-sm text-muted-foreground">
                    Nothing logged yet. Mark leads as sent on the Today page.
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
