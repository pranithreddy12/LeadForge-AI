"use client";

import { useQuery } from "@tanstack/react-query";
import { OrganizationProfile, UserProfile } from "@clerk/nextjs";
import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";

export default function SettingsPage() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => api.get("/auth/me") });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-muted-foreground">Manage your profile, organization and integrations.</p>
      </div>

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
    </div>
  );
}
