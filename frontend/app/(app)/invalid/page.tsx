"use client";

import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Link from "next/link";
import { Loader2, PhoneOff, MessageCircle, Instagram, RotateCcw } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type InvalidItem = {
  company_id: string;
  company_name: string;
  phone: string | null;
  wa_link: string | null;
  socials: { instagram?: string | null } & Record<string, string | null>;
  score: number | null;
  grade: string | null;
};
type InvalidResp = { count: number; items: InvalidItem[] };

function Row({ it }: { it: InvalidItem }) {
  const qc = useQueryClient();
  const restore = useMutation({
    mutationFn: () => api.post(`/today/${it.company_id}/restore-number`),
    onSuccess: () => { toast.success("Restored — back on Today"); qc.invalidateQueries({ queryKey: ["invalid-numbers"] }); },
    onError: (e: any) => toast.error(e?.message || "Failed"),
  });
  const ig = it.socials?.instagram;
  return (
    <div className="flex items-center gap-3 px-4 py-2.5 text-sm">
      <Link href={`/leads/${it.company_id}`} className="font-medium hover:underline truncate">{it.company_name}</Link>
      {it.grade && <span className="text-[11px] rounded border border-white/10 bg-white/5 px-1.5 py-0.5 text-muted-foreground">{it.grade}{it.score != null ? ` · ${it.score}` : ""}</span>}
      {it.phone && <span className="text-xs text-muted-foreground tabular-nums line-through">{it.phone}</span>}
      <div className="flex-1" />
      {ig && (
        <a href={ig} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] text-fuchsia-300 hover:text-fuchsia-200">
          <Instagram className="h-3 w-3" /> Instagram
        </a>
      )}
      {it.wa_link && (
        <a href={it.wa_link} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-[11px] text-emerald-300 hover:text-emerald-200"
           title="Try the number anyway">
          <MessageCircle className="h-3 w-3" /> Try WhatsApp
        </a>
      )}
      <Button size="sm" variant="outline" disabled={restore.isPending} onClick={() => restore.mutate()}
              title="Number fixed / found another — put this lead back on Today.">
        {restore.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <RotateCcw className="h-3.5 w-3.5" />} Restore
      </Button>
    </div>
  );
}

export default function InvalidNumbersPage() {
  const q = useQuery({
    queryKey: ["invalid-numbers"],
    queryFn: () => api.get<InvalidResp>("/today/invalid-numbers"),
    refetchOnMount: "always",
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Invalid numbers</h1>
        <p className="text-sm text-muted-foreground">
          Leads parked because their WhatsApp number is invalid or unreachable. Find another
          number (try their Instagram), then Restore to put them back on Today.
          {q.data && <> · <span className="tabular-nums">{q.data.count}</span> parked</>}
        </p>
      </div>

      {q.isLoading && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {q.data?.count === 0 && (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
          <PhoneOff className="mx-auto mb-2 h-6 w-6 opacity-50" />
          No parked numbers. Use “Bad number” on the <Link href="/today" className="text-brand-300 hover:underline">Today</Link> page when a WhatsApp number doesn&apos;t work.
        </CardContent></Card>
      )}

      {!!q.data?.count && (
        <Card>
          <CardContent className="p-0 divide-y divide-white/5">
            {q.data.items.map((it) => <Row key={it.company_id} it={it} />)}
          </CardContent>
        </Card>
      )}
    </div>
  );
}
