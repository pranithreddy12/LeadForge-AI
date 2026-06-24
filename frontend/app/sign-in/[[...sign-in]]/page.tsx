import Link from "next/link";
import { SignIn } from "@clerk/nextjs";
import { clerkConfigured } from "@/lib/clerk-config";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Sparkles, ArrowRight } from "lucide-react";

export default function SignInPage() {
  if (!clerkConfigured) return <DemoAuthCard />;
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <SignIn appearance={{ elements: { rootBox: "shadow-glow" } }} />
    </div>
  );
}

function DemoAuthCard() {
  return (
    <div className="min-h-screen flex items-center justify-center p-6">
      <Card className="max-w-md w-full">
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Sparkles className="h-4 w-4 text-brand-400" /> Demo mode
          </CardTitle>
          <CardDescription>
            Clerk authentication isn't configured, so sign-in is disabled. You're
            already signed in as the seeded demo user — jump straight into the app.
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-3">
          <Link href="/dashboard">
            <Button variant="glow" className="w-full gap-2">
              Enter LeadForge <ArrowRight className="h-4 w-4" />
            </Button>
          </Link>
          <p className="text-xs text-muted-foreground">
            To enable real sign-in, set <code className="text-foreground">NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY</code>
            {" "}and <code className="text-foreground">CLERK_SECRET_KEY</code>.
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
