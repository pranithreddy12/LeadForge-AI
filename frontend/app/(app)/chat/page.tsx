"use client";

import { useState } from "react";
import Link from "next/link";
import { useMutation } from "@tanstack/react-query";
import { Send, Sparkles, Loader2 } from "lucide-react";

import { api } from "@/lib/api";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

type Hit = { id: string; name: string; domain: string | null; industry: string | null; score: number | null; reasoning: string | null };
type Source = { title: string; url: string };
type ChatResponse = { answer: string; companies: Hit[]; sources: Source[] };
type Msg = { role: "user" | "assistant"; content: string; companies?: Hit[]; sources?: Source[] };

export default function ChatPage() {
  const [history, setHistory] = useState<Msg[]>([]);
  const [input, setInput] = useState("");

  const send = useMutation({
    mutationFn: (text: string) =>
      api.post<ChatResponse>("/chat", {
        messages: [...history, { role: "user", content: text }],
        use_web: true,
      }),
    onSuccess: (r, text) => {
      setHistory(h => [
        ...h,
        { role: "user", content: text },
        { role: "assistant", content: r.answer, companies: r.companies, sources: r.sources },
      ]);
      setInput("");
    },
  });

  return (
    <div className="space-y-5 max-w-4xl mx-auto">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight flex items-center gap-2">
          <Sparkles className="h-5 w-5 text-brand-400" /> Ask AI
        </h1>
        <p className="text-sm text-muted-foreground">
          Natural-language search across your CRM and the web. Try:{" "}
          <em>"SaaS companies hiring QA engineers in California"</em>.
        </p>
      </div>

      <div className="space-y-3">
        {history.map((m, i) => (
          <Card key={i} className={m.role === "user" ? "bg-card/40" : ""}>
            <CardContent className="p-4">
              <div className="text-[11px] uppercase tracking-wider text-muted-foreground mb-1">
                {m.role}
              </div>
              <div className="text-sm whitespace-pre-wrap leading-relaxed">{m.content}</div>
              {m.companies && m.companies.length > 0 && (
                <div className="mt-3 grid sm:grid-cols-2 gap-2">
                  {m.companies.map(c => (
                    <Link key={c.id} href={`/leads/${c.id}`}
                          className="rounded-md border border-white/5 p-2.5 hover:bg-white/[0.03] text-sm">
                      <div className="font-medium">{c.name}</div>
                      <div className="text-xs text-muted-foreground">{c.industry || c.domain}</div>
                    </Link>
                  ))}
                </div>
              )}
              {m.sources && m.sources.length > 0 && (
                <div className="mt-3 flex flex-wrap gap-2">
                  {m.sources.map((s, j) => (
                    <a key={j} href={s.url} target="_blank" rel="noreferrer"
                       className="text-[11px] underline text-brand-300">{s.title}</a>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardContent className="p-3 flex gap-2 items-end">
          <Textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            placeholder="Ask anything…"
            className="min-h-[64px]"
            onKeyDown={(e) => {
              if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
                e.preventDefault();
                if (input.trim()) send.mutate(input.trim());
              }
            }}
          />
          <Button variant="glow" disabled={!input.trim() || send.isPending}
                  onClick={() => send.mutate(input.trim())}>
            {send.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
            Send
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
