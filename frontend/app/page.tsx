import Link from "next/link";
import { Sparkles, Target, Workflow, Zap, ArrowRight, Check } from "lucide-react";
import { Button } from "@/components/ui/button";
import { clerkConfigured } from "@/lib/clerk-config";

export default function MarketingHome() {
  // In demo mode there's no auth, so CTAs go straight into the app.
  const ctaHref = clerkConfigured ? "/sign-up" : "/dashboard";
  return (
    <div className="min-h-screen">
      {/* nav */}
      <header className="sticky top-0 z-30 border-b border-white/5 bg-background/60 backdrop-blur-xl">
        <div className="container flex h-14 items-center justify-between">
          <div className="flex items-center gap-2 font-semibold">
            <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-brand-500 to-brand-700 shadow-glow">
              <Sparkles className="h-4 w-4 text-white" />
            </div>
            LeadForge<span className="text-muted-foreground"> · AI</span>
          </div>
          <nav className="hidden md:flex items-center gap-7 text-sm text-muted-foreground">
            <a href="#features">Features</a>
            <a href="#how">How it works</a>
            <Link href="/pricing">Pricing</Link>
          </nav>
          <div className="flex items-center gap-2">
            <Link href={ctaHref}><Button variant="ghost" size="sm">Sign in</Button></Link>
            <Link href={ctaHref}><Button size="sm" variant="glow">Get started</Button></Link>
          </div>
        </div>
      </header>

      {/* hero */}
      <section className="container pt-20 pb-24 text-center">
        <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-card/40 px-3 py-1 text-xs text-muted-foreground">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" />
          AI-native sales intelligence
        </div>
        <h1 className="mx-auto mt-6 max-w-3xl text-4xl md:text-6xl font-semibold tracking-tight leading-[1.05]">
          Find the accounts most likely to buy
          <span className="bg-gradient-to-r from-brand-300 via-brand-400 to-brand-200 bg-clip-text text-transparent"> right now.</span>
        </h1>
        <p className="mx-auto mt-6 max-w-2xl text-lg text-muted-foreground">
          LeadForge turns a one-sentence description of your business into an ICP, a list of ranked accounts, validated contacts, buying signals, and personalized outreach — all in minutes.
        </p>
        <div className="mt-8 flex items-center justify-center gap-3">
          <Link href={ctaHref}>
            <Button size="lg" variant="glow" className="gap-2">
              Start free <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <Link href="/pricing">
            <Button size="lg" variant="outline">See pricing</Button>
          </Link>
        </div>
      </section>

      {/* features */}
      <section id="features" className="container grid md:grid-cols-3 gap-4 pb-24">
        {[
          { icon: Sparkles, title: "AI ICP generator", desc: "Describe your business. We build the ICP, weights, and signal model." },
          { icon: Target,    title: "Buying-signal scoring", desc: "Hiring, funding, growth, launches, tech installs — all blended into a 0–100 score." },
          { icon: Workflow,  title: "Daily automations", desc: "Find → enrich → validate → outreach. On autopilot." },
        ].map(({ icon: Icon, title, desc }) => (
          <div key={title} className="glass rounded-2xl p-6">
            <div className="mb-4 flex h-10 w-10 items-center justify-center rounded-lg bg-brand-500/10 text-brand-300 border border-brand-500/20">
              <Icon className="h-5 w-5" />
            </div>
            <h3 className="font-semibold">{title}</h3>
            <p className="mt-1 text-sm text-muted-foreground">{desc}</p>
          </div>
        ))}
      </section>

      {/* how */}
      <section id="how" className="container py-16">
        <h2 className="text-3xl font-semibold tracking-tight text-center">How it works</h2>
        <div className="mt-10 grid md:grid-cols-4 gap-4">
          {[
            "Describe your business",
            "We generate your ICP",
            "We surface accounts + signals",
            "You send personalized outreach",
          ].map((step, i) => (
            <div key={step} className="glass-soft rounded-xl p-5">
              <div className="text-xs text-muted-foreground">Step {i + 1}</div>
              <div className="mt-1 font-medium">{step}</div>
            </div>
          ))}
        </div>
      </section>

      {/* cta */}
      <section className="container py-24">
        <div className="glass rounded-3xl p-10 text-center shadow-glow">
          <div className="inline-flex items-center gap-1 rounded-full bg-brand-500/10 border border-brand-500/20 px-3 py-1 text-xs text-brand-300">
            <Zap className="h-3 w-3" /> Built for B2B teams
          </div>
          <h2 className="mt-4 text-3xl font-semibold">Stop hunting. Start closing.</h2>
          <p className="mt-2 text-muted-foreground">Free for the first 50 leads. No credit card.</p>
          <div className="mt-6 flex items-center justify-center gap-3">
            <Link href={ctaHref}><Button size="lg" variant="glow">Try LeadForge</Button></Link>
          </div>
          <ul className="mt-8 flex flex-wrap justify-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
            {["GDPR-friendly", "Bring your own keys", "Cancel anytime"].map(b => (
              <li key={b} className="inline-flex items-center gap-1"><Check className="h-3 w-3 text-emerald-400" /> {b}</li>
            ))}
          </ul>
        </div>
      </section>

      <footer className="border-t border-white/5">
        <div className="container py-8 text-xs text-muted-foreground flex justify-between">
          <span>© {new Date().getFullYear()} LeadForge AI</span>
          <span>Built with Next.js, FastAPI, OpenAI.</span>
        </div>
      </footer>
    </div>
  );
}
