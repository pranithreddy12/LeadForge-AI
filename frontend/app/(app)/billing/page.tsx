"use client";

import { useMutation, useQuery } from "@tanstack/react-query";
import { Check, Zap } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Button } from "@/components/ui/button";

type Plan = "starter" | "growth" | "scale";

const PLANS: { id: Plan; price: string; perks: string[] }[] = [
  { id: "starter", price: "$49 / mo", perks: ["500 leads / mo", "Daily discovery", "Email validation"] },
  { id: "growth",  price: "$149 / mo", perks: ["5,000 leads / mo", "AI signal extraction", "Workflows", "Slack & webhook"] },
  { id: "scale",   price: "$499 / mo", perks: ["Unlimited leads", "Multi-org", "API access", "Priority support"] },
];

export default function BillingPage() {
  const { data: sub } = useQuery({
    queryKey: ["subscription"],
    queryFn: () => api.get<any>("/billing/subscription"),
  });

  const checkout = useMutation({
    mutationFn: (plan: Plan) => api.post<{ url: string }>("/billing/checkout", { plan }),
    onSuccess: (r) => { window.location.href = r.url; },
    onError: (e: any) => toast.error(e.message),
  });

  return (
    <div className="space-y-6 max-w-5xl">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Billing</h1>
        <p className="text-sm text-muted-foreground">
          Current plan: <span className="font-medium text-foreground">{sub?.plan || "free"}</span>
        </p>
      </div>

      <div className="grid md:grid-cols-3 gap-4">
        {PLANS.map(p => (
          <Card key={p.id} className={p.id === "growth" ? "shadow-glow" : ""}>
            <CardHeader>
              <CardTitle className="capitalize flex items-center gap-2">
                {p.id}
                {p.id === "growth" && <span className="text-[10px] rounded bg-brand-500/15 text-brand-300 px-1.5 py-0.5 border border-brand-500/20">Most popular</span>}
              </CardTitle>
              <CardDescription className="text-xl font-semibold text-foreground">{p.price}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="space-y-1.5 text-sm">
                {p.perks.map(perk => (
                  <li key={perk} className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-emerald-400" /> {perk}</li>
                ))}
              </ul>
              <Button
                variant={p.id === "growth" ? "glow" : "outline"}
                className="w-full"
                disabled={checkout.isPending || sub?.plan === p.id}
                onClick={() => checkout.mutate(p.id)}
              >
                <Zap className="h-3.5 w-3.5" />
                {sub?.plan === p.id ? "Current plan" : "Upgrade"}
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
