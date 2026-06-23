"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";

import { api } from "@/lib/api";
import type { Contact, Page as PageT } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";

export default function ContactsPage() {
  const [q, setQ] = useState("");
  const { data } = useQuery({
    queryKey: ["contacts-all"],
    queryFn: () => api.get<PageT<Contact>>("/contacts?page_size=100"),
  });

  const filtered = (data?.items || []).filter(c =>
    !q || c.name.toLowerCase().includes(q.toLowerCase())
       || (c.title || "").toLowerCase().includes(q.toLowerCase())
       || (c.email || "").toLowerCase().includes(q.toLowerCase())
  );

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Contacts</h1>
        <p className="text-sm text-muted-foreground">Decision makers across all your accounts.</p>
      </div>

      <Card className="p-3">
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
          <Input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search by name, title, email…"
            className="pl-9 h-9 bg-card/40"
          />
        </div>
      </Card>

      <Card>
        <CardHeader><CardTitle>{filtered.length} contacts</CardTitle></CardHeader>
        <CardContent className="p-0">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-muted-foreground border-b border-white/5">
                <th className="py-2 px-4">Name</th>
                <th>Title</th>
                <th>Seniority</th>
                <th>Email</th>
                <th>Status</th>
                <th className="pr-4 text-right">LinkedIn</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map(p => (
                <tr key={p.id} className="border-b border-white/5 hover:bg-white/[0.02]">
                  <td className="py-2.5 px-4 font-medium">{p.name}</td>
                  <td className="text-muted-foreground">{p.title}</td>
                  <td className="text-muted-foreground">{p.seniority || "—"}</td>
                  <td className="text-muted-foreground">{p.email || "—"}</td>
                  <td>
                    {p.email_status && (
                      <Badge variant={
                        p.email_status === "valid" ? "success" :
                        p.email_status === "risky" ? "warn" :
                        p.email_status === "invalid" ? "danger" : "default"
                      }>{p.email_status}{p.email_confidence ? ` · ${p.email_confidence}` : ""}</Badge>
                    )}
                  </td>
                  <td className="pr-4 text-right">
                    {p.linkedin_url && <a className="text-xs text-brand-300" href={p.linkedin_url} target="_blank" rel="noreferrer">Open ↗</a>}
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="py-10 text-center text-sm text-muted-foreground">
                  No contacts yet.
                </td></tr>
              )}
            </tbody>
          </table>
        </CardContent>
      </Card>
    </div>
  );
}
