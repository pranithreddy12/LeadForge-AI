import Link from "next/link";
import { Check, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default function Pricing() {
  return (
    <div className="container py-20">
      <header className="text-center mb-12">
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-card/40 px-3 py-1 text-xs text-muted-foreground">
          <Sparkles className="h-3.5 w-3.5 text-brand-400" /> Simple pricing
        </div>
        <h1 className="mt-4 text-4xl font-semibold tracking-tight">Plans that scale with your pipeline.</h1>
      </header>

      <div className="grid md:grid-cols-3 gap-4 max-w-5xl mx-auto">
        {[
          { id: "starter", title: "Starter", price: "$49", perks: ["500 leads / mo", "Daily discovery", "Email validation"] },
          { id: "growth",  title: "Growth",  price: "$149", perks: ["5,000 leads / mo", "AI signal extraction", "Workflows", "Slack & webhook"], featured: true },
          { id: "scale",   title: "Scale",   price: "$499", perks: ["Unlimited leads", "Multi-org", "API access", "Priority support"] },
        ].map(p => (
          <Card key={p.id} className={p.featured ? "shadow-glow" : ""}>
            <CardHeader>
              <CardTitle>{p.title}</CardTitle>
              <CardDescription className="text-2xl font-semibold text-foreground">{p.price}<span className="text-sm font-normal text-muted-foreground"> / mo</span></CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <ul className="space-y-1.5 text-sm">
                {p.perks.map(perk => (
                  <li key={perk} className="flex items-center gap-2"><Check className="h-3.5 w-3.5 text-emerald-400" /> {perk}</li>
                ))}
              </ul>
              <Link href="/sign-up"><Button variant={p.featured ? "glow" : "outline"} className="w-full">Get started</Button></Link>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
