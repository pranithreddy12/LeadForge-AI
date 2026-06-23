"use client";

import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Loader2, Play, Plus, Workflow as WorkflowIcon } from "lucide-react";
import { toast } from "sonner";

import { api } from "@/lib/api";
import type { Workflow } from "@/lib/types";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";

const TEMPLATES = [
  {
    name: "Daily — discover & score SaaS",
    description: "Every day: discover new SaaS companies, detect signals, score against your ICP, add hot leads to CRM.",
    schedule: "daily",
    steps: [
      { id: "s1", type: "discover_companies", config: { limit: 20 }, next: ["s2"] },
      { id: "s2", type: "detect_signals", config: {}, next: ["s3"] },
      { id: "s3", type: "find_contacts", config: {}, next: ["s4"] },
      { id: "s4", type: "validate_emails", config: {}, next: ["s5"] },
      { id: "s5", type: "score_leads", config: {}, next: ["s6"] },
      { id: "s6", type: "filter", config: { min_score: 75 }, next: ["s7"] },
      { id: "s7", type: "add_to_crm", config: { stage: "qualified" }, next: [] },
    ],
  },
  {
    name: "Hourly — refresh signals",
    description: "Sweep new buying signals across already-known accounts every hour.",
    schedule: "hourly",
    steps: [
      { id: "s1", type: "detect_signals", config: {}, next: [] },
    ],
  },
];

export default function WorkflowsPage() {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ["workflows"],
    queryFn: () => api.get<Workflow[]>("/workflows"),
  });

  const create = useMutation({
    mutationFn: (payload: any) => api.post<Workflow>("/workflows", payload),
    onSuccess: () => { toast.success("Workflow created"); qc.invalidateQueries({ queryKey: ["workflows"] }); },
  });
  const run = useMutation({
    mutationFn: (id: string) => api.post(`/workflows/${id}/run`),
    onSuccess: () => toast.success("Workflow queued"),
  });

  return (
    <div className="space-y-5">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Automation workflows</h1>
          <p className="text-sm text-muted-foreground">
            Daily / hourly pipelines that discover, enrich, score, and queue outreach.
          </p>
        </div>
        <NewWorkflowDialog onCreate={(p) => create.mutate(p)} />
      </div>

      <div className="grid sm:grid-cols-2 gap-3">
        {TEMPLATES.map(t => (
          <Card key={t.name}>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <WorkflowIcon className="h-4 w-4 text-brand-400" /> {t.name}
                <Badge variant="outline">{t.schedule}</Badge>
              </CardTitle>
              <CardDescription>{t.description}</CardDescription>
            </CardHeader>
            <CardContent>
              <Button variant="outline" size="sm" onClick={() => create.mutate(t)} disabled={create.isPending}>
                <Plus className="h-3.5 w-3.5" /> Use template
              </Button>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card>
        <CardHeader><CardTitle>Your workflows</CardTitle></CardHeader>
        <CardContent className="p-0">
          {data && data.length > 0 ? (
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-xs text-muted-foreground border-b border-white/5">
                  <th className="py-2 px-4">Name</th>
                  <th>Schedule</th>
                  <th>Steps</th>
                  <th>Last run</th>
                  <th className="pr-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody>
                {data.map(w => (
                  <tr key={w.id} className="border-b border-white/5">
                    <td className="py-2.5 px-4 font-medium">{w.name}</td>
                    <td><Badge variant="outline">{w.schedule}</Badge></td>
                    <td className="text-muted-foreground">{w.steps?.length || 0}</td>
                    <td className="text-muted-foreground">{w.last_run_at || "never"}</td>
                    <td className="pr-4 text-right">
                      <Button size="sm" variant="outline" onClick={() => run.mutate(w.id)}>
                        <Play className="h-3 w-3" /> Run
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <div className="p-8 text-center text-sm text-muted-foreground">
              No workflows yet — start from a template above.
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function NewWorkflowDialog({ onCreate }: { onCreate: (p: any) => void }) {
  const [name, setName] = useState("");
  const [desc, setDesc] = useState("");
  const [schedule, setSchedule] = useState("manual");

  return (
    <Dialog>
      <DialogTrigger asChild>
        <Button variant="glow"><Plus className="h-4 w-4" /> New workflow</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader><DialogTitle>New workflow</DialogTitle></DialogHeader>
        <Input placeholder="Name" value={name} onChange={e => setName(e.target.value)} />
        <Textarea placeholder="Description" value={desc} onChange={e => setDesc(e.target.value)} />
        <select value={schedule} onChange={e => setSchedule(e.target.value)}
                className="h-9 rounded-md bg-card/40 border border-input px-3 text-sm">
          <option value="manual">manual</option>
          <option value="hourly">hourly</option>
          <option value="daily">daily</option>
        </select>
        <div className="flex justify-end">
          <Button variant="glow" onClick={() => onCreate({ name, description: desc, schedule, steps: [] })}>
            Create
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
