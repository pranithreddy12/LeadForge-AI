"use client";

import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Download, Loader2, Search, ArrowUpDown, RefreshCw } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

type Row = Record<string, any> & { id: string; name: string };
type DataResp = { count: number; columns: string[]; rows: Row[] };

// Human labels for the raw column keys.
const LABELS: Record<string, string> = {
  name: "Name", domain: "Domain", website: "Website", city: "City",
  country: "Country", industry: "Industry", phone: "Phone", phone_intl: "Phone (intl)",
  rating: "Rating", review_count: "Reviews", hours: "Hours",
  online_booking: "Online booking", score: "Score", grade: "Grade",
  top_signal: "Top signal", signals: "Signals", pipeline_stage: "Stage",
  source: "Source", contact_name: "Contact", contact_email: "Email",
  decision_maker: "Decision maker", linkedin_url: "LinkedIn", instagram: "Instagram",
  place_id: "Place ID", created_at: "Found",
};

function fmtCell(key: string, v: any): string {
  if (v === null || v === undefined || v === "") return "—";
  if (key === "created_at") return new Date(v).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
  if (key === "online_booking") return v === true ? "yes" : v === false ? "no" : "—";
  if (typeof v === "boolean") return v ? "yes" : "no";
  return String(v);
}

function toCsv(columns: string[], rows: Row[]): string {
  const esc = (s: any) => {
    const str = s === null || s === undefined ? "" : String(s);
    return /[",\n]/.test(str) ? `"${str.replace(/"/g, '""')}"` : str;
  };
  const head = columns.map((c) => esc(LABELS[c] || c)).join(",");
  const body = rows.map((r) => columns.map((c) => esc(fmtCell(c, r[c]) === "—" ? "" : r[c])).join(",")).join("\n");
  return `${head}\n${body}`;
}

export default function DataPage() {
  const [q, setQ] = useState("");
  const [sortKey, setSortKey] = useState<string>("created_at");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("desc");

  const query = useQuery({
    queryKey: ["scraped-data"],
    queryFn: () => api.get<DataResp>("/data/leads"),
    // Always show the freshest data — new leads land after every discovery run.
    refetchOnMount: "always",
    staleTime: 0,
  });

  const columns = query.data?.columns ?? [];
  const rows = query.data?.rows ?? [];

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    let out = rows;
    if (needle) {
      out = rows.filter((r) =>
        columns.some((c) => String(r[c] ?? "").toLowerCase().includes(needle)));
    }
    const dir = sortDir === "asc" ? 1 : -1;
    return [...out].sort((a, b) => {
      const av = a[sortKey], bv = b[sortKey];
      if (av === null || av === undefined) return 1;   // nulls last
      if (bv === null || bv === undefined) return -1;
      if (typeof av === "number" && typeof bv === "number") return (av - bv) * dir;
      return String(av).localeCompare(String(bv)) * dir;
    });
  }, [rows, columns, q, sortKey, sortDir]);

  function sortBy(key: string) {
    if (key === sortKey) setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    else { setSortKey(key); setSortDir("asc"); }
  }

  function download() {
    if (!filtered.length) { toast.error("Nothing to export"); return; }
    const csv = toCsv(columns, filtered);
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `leadforge-scraped-data-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
    toast.success(`Exported ${filtered.length} row${filtered.length === 1 ? "" : "s"}`);
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold">Scraped Data</h1>
          <p className="text-sm text-muted-foreground">
            Every discovered lead with all collected fields. Search, sort any column, export to CSV.
            {query.data && <> · <span className="tabular-nums">{filtered.length}</span> of {query.data.count} shown</>}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="pointer-events-none absolute left-2.5 top-2.5 h-4 w-4 text-muted-foreground" />
            <Input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search all fields…"
                   className="w-56 pl-8" />
          </div>
          <Button variant="outline" onClick={() => query.refetch()} disabled={query.isFetching}>
            <RefreshCw className={`h-4 w-4 ${query.isFetching ? "animate-spin" : ""}`} /> Refresh
          </Button>
          <Button variant="outline" onClick={download} disabled={!filtered.length}>
            <Download className="h-4 w-4" /> CSV
          </Button>
        </div>
      </div>

      {query.isLoading && <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />}
      {query.data?.count === 0 && (
        <Card><CardContent className="py-10 text-center text-sm text-muted-foreground">
          No leads collected yet. Run discovery from the Today page.
        </CardContent></Card>
      )}

      {!!filtered.length && (
        <Card>
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="border-b border-white/10 text-left">
                    {columns.map((c) => (
                      <th key={c} className="whitespace-nowrap px-3 py-2 font-medium text-muted-foreground">
                        <button onClick={() => sortBy(c)}
                                className="inline-flex items-center gap-1 hover:text-foreground">
                          {LABELS[c] || c}
                          <ArrowUpDown className={`h-3 w-3 ${sortKey === c ? "text-brand-300" : "opacity-40"}`} />
                        </button>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((r) => (
                    <tr key={r.id} className="border-b border-white/5 hover:bg-white/5">
                      {columns.map((c) => (
                        <td key={c} className="max-w-[240px] truncate whitespace-nowrap px-3 py-2"
                            title={fmtCell(c, r[c])}>
                          {c === "grade" && r[c]
                            ? <Badge variant="brand">{r[c]}</Badge>
                            : c === "website" && r[c]
                            ? <a href={r[c]} target="_blank" rel="noopener noreferrer" className="text-brand-300 hover:underline">{r[c]}</a>
                            : fmtCell(c, r[c])}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
