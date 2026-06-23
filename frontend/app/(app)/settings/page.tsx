"use client";

import { useQuery } from "@tanstack/react-query";
import { OrganizationProfile, UserProfile } from "@clerk/nextjs";
import { api } from "@/lib/api";
import { clerkConfigured } from "@/lib/clerk-config";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";

export default function SettingsPage() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.get<any>("/auth/me") });
  const org = useQuery({ queryKey: ["org"], queryFn: () => api.get<any>("/auth/org") });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your profile, organization and integrations.</p>
      </div>

      {clerkConfigured ? (
        <Tabs defaultValue="profile">
          <TabsList>
            <TabsTrigger value="profile">Profile</TabsTrigger>
            <TabsTrigger value="org">Organization</TabsTrigger>
          </TabsList>
          <TabsContent value="profile">
            <UserProfile routing="hash" appearance={{ elements: { rootBox: "w-full" } }} />
          </TabsContent>
          <TabsContent value="org">
            <OrganizationProfile routing="hash" appearance={{ elements: { rootBox: "w-full" } }} />
          </TabsContent>
        </Tabs>
      ) : (
        <Card>
          <CardHeader>
            <CardTitle>Demo mode</CardTitle>
            <CardDescription>
              Clerk isn't configured, so profile management is read-only. Set
              NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY and CLERK_SECRET_KEY to enable real auth.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-3 text-sm">
            <Row label="Signed in as" value={me.data?.name || me.data?.email || "Demo Founder"} />
            <Row label="Email" value={me.data?.email || "founder@demo.co"} />
            <Row label="Organization" value={org.data?.name || "Demo Co"} />
            <Row label="Plan" value={org.data?.plan || "growth"} />
          </CardContent>
        </Card>
      )}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-white/5 pb-2">
      <span className="text-muted-foreground">{label}</span>
      <span className="font-medium">{value}</span>
    </div>
  );
}
