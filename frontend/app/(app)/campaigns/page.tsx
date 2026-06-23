"use client";

import { useQuery } from "@tanstack/react-query";
import { Send } from "lucide-react";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Page as PageT } from "@/lib/types";

type Campaign = { id: string; name: string; objective?: string | null; channel: string; status: string; created_at: string };

export default function CampaignsPage() {
  const { data } = useQuery({
    queryKey: ["campaigns"],
    queryFn: () => api.get<PageT<Campaign>>("/campaigns?page_size=50"),
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Campaigns</h1>
        <p className="text-sm text-muted-foreground">Outreach sequences across your accounts.</p>
      </div>

      <Card>
        <CardHeader><CardTitle>{data?.total ?? 0} campaigns</CardTitle></CardHeader>
        <CardContent className="p-0">
          {data && data.items.length > 0 ? (
            <table className="w-full text-sm">
              <thead><tr className="text-left text-xs text-muted-foreground border-b border-white/5">
                <th className="py-2 px-4">Name</th><th>Channel</th><th>Status</th><th>Objective</th>
              </tr></thead>
              <tbody>
                {data.items.map(c => (
                  <tr key={c.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                    <td className="py-2.5 px-4 font-medium">{c.name}</td>
                    <td><Badge variant="info">{c.channel}</Badge></td>
                    <td><Badge variant={c.status === "active" ? "success" : "default"}>{c.status}</Badge></td>
                    <td className="text-muted-foreground">{c.objective || "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-8 text-center text-sm text-muted-foreground flex flex-col items-center gap-2">
              <Send className="h-6 w-6 text-brand-400/60" />
              No campaigns yet. Generate outreach from any lead's detail page.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
