"use client";

import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";

import { api } from "@/lib/api";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";

type Creds = {
  gmail_address: string | null;
  telegram_chat_id: string | null;
  gmail_app_password_set: boolean;
  telegram_bot_token_set: boolean;
  google_places_api_key_set: boolean;
  whatsapp_phone_number_id: string | null;
  whatsapp_business_account_id: string | null;
  whatsapp_access_token_set: boolean;
  whatsapp_verify_token_set: boolean;
  hunter_api_key_set: boolean;
};
type SettingsData = {
  discovery_mode: "b2b" | "local";
  target_business_types: string[];
  target_locations: string[];
  search_radius_miles: number;
  min_reviews: number;
  max_results_per_run: number;
  icp_name: string | null;
  employee_min: number | null;
  employee_max: number | null;
  target_industries: string[];
  target_geography: string[];
  outreach_mode: string[];
  outreach_tone: "professional" | "friendly" | "direct";
  outreach_send_mode: "manual" | "automated";
  booking_link: string | null;
  portfolio_link: string | null;
  draft_language: "en" | "en+ar";
  outreach_services: string | null;
  max_emails_per_day: number;
  max_emails_per_run: number;
  contact_find_hunter: boolean;
  contact_find_scrape: boolean;
  contact_find_linkedin: boolean;
  validate_emails: boolean;
  filter_min_score: number;
  filter_enforce_icp_size: boolean;
  whatsapp_webhook_url: string;
  credentials: Creds;
};

function TagInput({ value, onChange, placeholder }: {
  value: string[]; onChange: (v: string[]) => void; placeholder: string;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const t = draft.trim();
    if (t && !value.includes(t)) onChange([...value, t]);
    setDraft("");
  };
  return (
    <div>
      <div className="flex gap-2">
        <Input
          value={draft}
          placeholder={placeholder}
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }}
        />
        <Button type="button" variant="outline" onClick={add}>Add</Button>
      </div>
      <div className="mt-2 flex flex-wrap gap-1.5">
        {value.map((t) => (
          <Badge key={t} variant="outline" className="cursor-pointer"
                 onClick={() => onChange(value.filter((x) => x !== t))}>
            {t} <span className="ml-1 opacity-60">x</span>
          </Badge>
        ))}
        {value.length === 0 && <span className="text-xs text-muted-foreground">none yet</span>}
      </div>
    </div>
  );
}

function Field({ label, children, hint }: { label: string; children: React.ReactNode; hint?: string }) {
  return (
    <div className="space-y-1.5">
      <label className="text-sm font-medium">{label}</label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Toggle({ label, hint, value, onChange }: {
  label: string; hint?: string; value: boolean; onChange: (v: boolean) => void;
}) {
  return (
    <div className="flex items-center justify-between gap-3 py-1.5">
      <div>
        <div className="text-sm font-medium">{label}</div>
        {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
      </div>
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative h-6 w-11 shrink-0 rounded-full transition-colors ${value ? "bg-green-500" : "bg-white/15"}`}
      >
        <span className={`absolute top-0.5 h-5 w-5 rounded-full bg-white transition-all ${value ? "left-[22px]" : "left-0.5"}`} />
      </button>
    </div>
  );
}

function CredDot({ set }: { set: boolean }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs whitespace-nowrap">
      <span className={`h-2.5 w-2.5 rounded-full ${set ? "bg-green-500" : "bg-red-400"}`} />
      {set ? "set" : "not set"}
    </span>
  );
}

const EMPTY: SettingsData = {
  discovery_mode: "b2b", target_business_types: [], target_locations: [],
  search_radius_miles: 25, min_reviews: 10, max_results_per_run: 20,
  icp_name: "", employee_min: null, employee_max: null, target_industries: [], target_geography: [],
  outreach_mode: ["email"], outreach_tone: "professional", outreach_send_mode: "manual", booking_link: "", portfolio_link: "", draft_language: "en", outreach_services: "", max_emails_per_day: 50, max_emails_per_run: 25,
  contact_find_hunter: true, contact_find_scrape: true, contact_find_linkedin: true, validate_emails: true,
  filter_min_score: 65, filter_enforce_icp_size: true,
  whatsapp_webhook_url: "",
  credentials: { gmail_address: "", telegram_chat_id: "", gmail_app_password_set: false, telegram_bot_token_set: false, google_places_api_key_set: false, whatsapp_phone_number_id: "", whatsapp_business_account_id: "", whatsapp_access_token_set: false, whatsapp_verify_token_set: false, hunter_api_key_set: false },
};

export default function SettingsPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["settings"], queryFn: () => api.get<SettingsData>("/settings"),
  });
  const [f, setF] = useState<SettingsData>(EMPTY);
  const [err, setErr] = useState<string | null>(null);
  const [secrets, setSecrets] = useState({ gmail_app_password: "", telegram_bot_token: "", google_places_api_key: "", whatsapp_access_token: "", whatsapp_verify_token: "", hunter_api_key: "" });

  useEffect(() => { if (data) setF(data); }, [data]);

  const save = useMutation({
    mutationFn: (body: any) => api.put("/settings", body),
    onSuccess: () => {
      toast.success("Settings saved");
      qc.invalidateQueries({ queryKey: ["settings"] });
      setSecrets({ gmail_app_password: "", telegram_bot_token: "", google_places_api_key: "", whatsapp_access_token: "", whatsapp_verify_token: "", hunter_api_key: "" });
    },
    onError: (e: any) => toast.error(e?.message || "Save failed"),
  });

  if (isLoading) return <div className="text-sm text-muted-foreground">Loading settings...</div>;

  const set = (patch: Partial<SettingsData>) => setF({ ...f, ...patch });

  function onSave() {
    setErr(null);
    if (f.discovery_mode === "local") {
      if (f.target_business_types.length === 0) { setErr("Local mode: add at least one business type."); return; }
      if (f.target_locations.length === 0) { setErr("Local mode: add at least one location."); return; }
    } else {
      if (!f.icp_name?.trim()) { setErr("B2B mode: ICP name is required."); return; }
      if (f.target_industries.length === 0) { setErr("B2B mode: add at least one industry."); return; }
    }
    const body: any = {
      discovery_mode: f.discovery_mode,
      target_business_types: f.target_business_types, target_locations: f.target_locations,
      search_radius_miles: f.search_radius_miles, min_reviews: f.min_reviews, max_results_per_run: f.max_results_per_run,
      icp_name: f.icp_name, employee_min: f.employee_min, employee_max: f.employee_max,
      target_industries: f.target_industries, target_geography: f.target_geography,
      outreach_mode: f.outreach_mode, outreach_tone: f.outreach_tone,
      outreach_send_mode: f.outreach_send_mode, booking_link: f.booking_link ?? "", portfolio_link: f.portfolio_link ?? "",
      draft_language: f.draft_language, outreach_services: f.outreach_services ?? "",
      max_emails_per_day: f.max_emails_per_day, max_emails_per_run: f.max_emails_per_run,
      contact_find_hunter: f.contact_find_hunter, contact_find_scrape: f.contact_find_scrape,
      contact_find_linkedin: f.contact_find_linkedin, validate_emails: f.validate_emails,
      filter_min_score: f.filter_min_score, filter_enforce_icp_size: f.filter_enforce_icp_size,
      gmail_address: f.credentials.gmail_address ?? "", telegram_chat_id: f.credentials.telegram_chat_id ?? "",
      whatsapp_phone_number_id: f.credentials.whatsapp_phone_number_id ?? "",
      whatsapp_business_account_id: f.credentials.whatsapp_business_account_id ?? "",
    };
    if (secrets.gmail_app_password) body.gmail_app_password = secrets.gmail_app_password;
    if (secrets.telegram_bot_token) body.telegram_bot_token = secrets.telegram_bot_token;
    if (secrets.google_places_api_key) body.google_places_api_key = secrets.google_places_api_key;
    if (secrets.whatsapp_access_token) body.whatsapp_access_token = secrets.whatsapp_access_token;
    if (secrets.whatsapp_verify_token) body.whatsapp_verify_token = secrets.whatsapp_verify_token;
    if (secrets.hunter_api_key) body.hunter_api_key = secrets.hunter_api_key;
    save.mutate(body);
  }

  const numIn = (v: number | null, on: (n: number) => void) => (
    <Input type="number" value={v ?? ""} onChange={(e) => on(Number(e.target.value))} className="max-w-[160px]" />
  );

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
          <p className="text-sm text-muted-foreground">Controls discovery, outreach, and notifications. The daily engine reads from here.</p>
        </div>
        <Button onClick={onSave} disabled={save.isPending}>{save.isPending ? "Saving..." : "Save"}</Button>
      </div>
      {err && <div className="rounded-md border border-red-300 bg-red-50 px-3 py-2 text-sm text-red-700">{err}</div>}

      <Tabs defaultValue="discovery">
        <TabsList>
          <TabsTrigger value="discovery">Discovery</TabsTrigger>
          <TabsTrigger value="outreach">Outreach + Notifications</TabsTrigger>
        </TabsList>

        <TabsContent value="discovery" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Discovery mode</CardTitle>
              <CardDescription>How the daily engine finds leads.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                {(["b2b", "local"] as const).map((m) => (
                  <Button key={m} variant={f.discovery_mode === m ? "default" : "outline"}
                          onClick={() => set({ discovery_mode: m })}>
                    {m === "b2b" ? "B2B (web search)" : "Local Business (Google Places)"}
                  </Button>
                ))}
              </div>
              <Separator />

              {f.discovery_mode === "local" ? (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="Target business types" hint="e.g. med spa, dental clinic, law firm">
                    <TagInput value={f.target_business_types} onChange={(v) => set({ target_business_types: v })} placeholder="Add a business type + Enter" />
                  </Field>
                  <Field label="Target locations" hint="e.g. Dallas TX, Houston TX">
                    <TagInput value={f.target_locations} onChange={(v) => set({ target_locations: v })} placeholder="Add a location + Enter" />
                  </Field>
                  <Field label="Search radius (miles)">{numIn(f.search_radius_miles, (n) => set({ search_radius_miles: n }))}</Field>
                  <Field label="Minimum reviews">{numIn(f.min_reviews, (n) => set({ min_reviews: n }))}</Field>
                  <Field label="Max results per run">{numIn(f.max_results_per_run, (n) => set({ max_results_per_run: n }))}</Field>
                </div>
              ) : (
                <div className="grid gap-4 sm:grid-cols-2">
                  <Field label="ICP name">
                    <Input value={f.icp_name ?? ""} onChange={(e) => set({ icp_name: e.target.value })} placeholder="e.g. Mid-market B2B SaaS" />
                  </Field>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label="Employee min">{numIn(f.employee_min, (n) => set({ employee_min: n }))}</Field>
                    <Field label="Employee max">{numIn(f.employee_max, (n) => set({ employee_max: n }))}</Field>
                  </div>
                  <Field label="Target industries" hint="verticals you sell into">
                    <TagInput value={f.target_industries} onChange={(v) => set({ target_industries: v })} placeholder="Add an industry + Enter" />
                  </Field>
                  <Field label="Target geography" hint="countries / regions">
                    <TagInput value={f.target_geography} onChange={(v) => set({ target_geography: v })} placeholder="Add a country + Enter" />
                  </Field>
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Contact finding</CardTitle>
              <CardDescription>How the pipeline finds a contact email for each lead. Turn sources on/off.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-1 divide-y divide-white/5">
              <Toggle label="Hunter.io domain search" hint="Highest-confidence emails (needs a Hunter API key)."
                      value={f.contact_find_hunter} onChange={(v) => set({ contact_find_hunter: v })} />
              <Toggle label="Website email scraping" hint="Fallback: scrape role inboxes (sales@/info@) from the site."
                      value={f.contact_find_scrape} onChange={(v) => set({ contact_find_scrape: v })} />
              <Toggle label="LinkedIn / SERP names" hint="Find decision-maker names + titles via search."
                      value={f.contact_find_linkedin} onChange={(v) => set({ contact_find_linkedin: v })} />
              <Toggle label="Validate emails" hint="Verify deliverability (Hunter/NeverBounce) before outreach."
                      value={f.validate_emails} onChange={(v) => set({ validate_emails: v })} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Lead quality filter</CardTitle>
              <CardDescription>The bar a lead must clear to reach outreach. Quality over volume.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Minimum score" hint="0-100. Leads scoring below this are dropped before outreach.">
                {numIn(f.filter_min_score, (n) => set({ filter_min_score: n }))}
              </Field>
              <Toggle label="Enforce ICP size band" hint="Hard-drop companies outside your employee_min/max, regardless of score."
                      value={f.filter_enforce_icp_size} onChange={(v) => set({ filter_enforce_icp_size: v })} />
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="outreach" className="space-y-4">
          <Card>
            <CardHeader><CardTitle>Outreach</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <Field label="Send mode" hint="Manual = the daily engine drafts only; you review + send each on the Today page. Automated = the engine sends automatically.">
                <div className="flex gap-2">
                  {([["manual", "Manual review"], ["automated", "Automated send"]] as const).map(([v, label]) => (
                    <Button key={v} variant={f.outreach_send_mode === v ? "default" : "outline"} onClick={() => set({ outreach_send_mode: v })}>{label}</Button>
                  ))}
                </div>
                {f.outreach_send_mode === "automated" && (
                  <p className="mt-2 text-xs text-amber-500">Automated mode sends real emails/WhatsApp without review. Keep Manual until you trust the drafts.</p>
                )}
              </Field>
              <Field label="Booking link" hint="Calendly/Cal.com/etc. Kept OUT of the cold first email (deliverability), then added to FOLLOW-UPS and reply drafts as a 'grab a call' CTA to help close.">
                <Input value={f.booking_link ?? ""} onChange={(e) => set({ booking_link: e.target.value })} placeholder="https://cal.com/you/15min (optional)" />
              </Field>
              <Field label="Portfolio link" hint="Examples / past work to share when a lead asks for more. Used in follow-ups and 'send info' replies — never in the cold first email.">
                <Input value={f.portfolio_link ?? ""} onChange={(e) => set({ portfolio_link: e.target.value })} placeholder="https://yoursite.com/work (optional)" />
              </Field>
              <Field label="Other services" hint="Comma-separated. The FIRST is your primary offer (the email's hook); the rest become a short P.S. line — 'We also set up X, Y…'. Only list what you genuinely deliver.">
                <Input value={f.outreach_services ?? ""} onChange={(e) => set({ outreach_services: e.target.value })}
                       placeholder="AI receptionist, WhatsApp booking automation, review management, missed-call text-back" />
              </Field>
              <Separator />
              <Field label="Draft language" hint="English + Arabic adds a natural Arabic version of the WhatsApp/DM message to every draft (UAE/GCC: Arabic-first owners reply more).">
                <div className="flex gap-2">
                  {([["en", "English only"], ["en+ar", "English + Arabic DM"]] as const).map(([v, label]) => (
                    <Button key={v} variant={f.draft_language === v ? "default" : "outline"} onClick={() => set({ draft_language: v })}>{label}</Button>
                  ))}
                </div>
              </Field>
              <Field label="Tone">
                <div className="flex gap-2">
                  {(["professional", "friendly", "direct"] as const).map((t) => (
                    <Button key={t} variant={f.outreach_tone === t ? "default" : "outline"} onClick={() => set({ outreach_tone: t })}>{t}</Button>
                  ))}
                </div>
              </Field>
              <div className="grid grid-cols-2 gap-3 max-w-sm">
                <Field label="Max emails / day">{numIn(f.max_emails_per_day, (n) => set({ max_emails_per_day: n }))}</Field>
                <Field label="Max emails / run">{numIn(f.max_emails_per_run, (n) => set({ max_emails_per_run: n }))}</Field>
              </div>
              <p className="text-xs text-muted-foreground">Note: only Email is sent automatically. SMS / call-script outputs are drafts to copy and use manually.</p>
            </CardContent>
          </Card>

          <DeliverabilityCard />

          <Card>
            <CardHeader>
              <CardTitle>Credentials + Notifications</CardTitle>
              <CardDescription>Stored encrypted. We never show saved secret values, only whether they are set.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Gmail address">
                <Input value={f.credentials.gmail_address ?? ""} onChange={(e) => set({ credentials: { ...f.credentials, gmail_address: e.target.value } })} placeholder="you@gmail.com" />
              </Field>
              <Field label="Gmail app password">
                <div className="flex items-center gap-3">
                  <Input type="password" value={secrets.gmail_app_password} onChange={(e) => setSecrets({ ...secrets, gmail_app_password: e.target.value })} placeholder="leave blank to keep current" />
                  <CredDot set={f.credentials.gmail_app_password_set} />
                </div>
              </Field>
              <Separator />
              <Field label="Telegram bot token">
                <div className="flex items-center gap-3">
                  <Input type="password" value={secrets.telegram_bot_token} onChange={(e) => setSecrets({ ...secrets, telegram_bot_token: e.target.value })} placeholder="leave blank to keep current" />
                  <CredDot set={f.credentials.telegram_bot_token_set} />
                </div>
              </Field>
              <Field label="Telegram chat id">
                <Input value={f.credentials.telegram_chat_id ?? ""} onChange={(e) => set({ credentials: { ...f.credentials, telegram_chat_id: e.target.value } })} placeholder="123456789" />
              </Field>
              <Separator />
              <Field label="Google Places API key" hint="required for Local Business discovery">
                <div className="flex items-center gap-3">
                  <Input type="password" value={secrets.google_places_api_key} onChange={(e) => setSecrets({ ...secrets, google_places_api_key: e.target.value })} placeholder="leave blank to keep current" />
                  <CredDot set={f.credentials.google_places_api_key_set} />
                </div>
              </Field>
              <Separator />
              <Field label="Hunter.io API key" hint="finds decision-maker emails by domain (secondary contact for local; primary email-finder for B2B)">
                <div className="flex items-center gap-3">
                  <Input type="password" value={secrets.hunter_api_key} onChange={(e) => setSecrets({ ...secrets, hunter_api_key: e.target.value })} placeholder="leave blank to keep current" />
                  <CredDot set={f.credentials.hunter_api_key_set} />
                </div>
              </Field>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>WhatsApp (Meta Cloud API)</CardTitle>
              <CardDescription>First-touch outreach channel for local businesses. Email is the 48h fallback if there is no reply.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <Field label="Phone number ID" hint="Meta -> WhatsApp -> API Setup (the ID, not the number)">
                <div className="flex items-center gap-3">
                  <Input value={f.credentials.whatsapp_phone_number_id ?? ""} onChange={(e) => set({ credentials: { ...f.credentials, whatsapp_phone_number_id: e.target.value } })} placeholder="123456789012345" />
                  <CredDot set={!!f.credentials.whatsapp_phone_number_id} />
                </div>
              </Field>
              <Field label="Business account ID (WABA)">
                <div className="flex items-center gap-3">
                  <Input value={f.credentials.whatsapp_business_account_id ?? ""} onChange={(e) => set({ credentials: { ...f.credentials, whatsapp_business_account_id: e.target.value } })} placeholder="123456789012345" />
                  <CredDot set={!!f.credentials.whatsapp_business_account_id} />
                </div>
              </Field>
              <Field label="Access token" hint="permanent System User token">
                <div className="flex items-center gap-3">
                  <Input type="password" value={secrets.whatsapp_access_token} onChange={(e) => setSecrets({ ...secrets, whatsapp_access_token: e.target.value })} placeholder="leave blank to keep current" />
                  <CredDot set={f.credentials.whatsapp_access_token_set} />
                </div>
              </Field>
              <Field label="Verify token" hint="any string you choose; paste the same value into the Meta webhook console">
                <div className="flex items-center gap-3">
                  <Input type="password" value={secrets.whatsapp_verify_token} onChange={(e) => setSecrets({ ...secrets, whatsapp_verify_token: e.target.value })} placeholder="leave blank to keep current" />
                  <CredDot set={f.credentials.whatsapp_verify_token_set} />
                </div>
              </Field>
              <Separator />
              <Field label="Webhook URL (read-only)" hint="Paste this into Meta -> WhatsApp -> Configuration -> Webhook -> Callback URL">
                <Input readOnly value={f.whatsapp_webhook_url} onFocus={(e) => e.currentTarget.select()} className="font-mono text-xs" />
              </Field>
            </CardContent>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}

type AuthCheck = {
  domain: string;
  spf: { found: boolean; record: string | null };
  dmarc: { found: boolean; policy: string | null; record: string | null };
  dkim: { found: boolean; selector: string | null };
  mx: boolean | null;
  verdict: "pass" | "partial" | "fail" | "unknown";
  notes: string[];
};

function DeliverabilityCard() {
  const [domain, setDomain] = useState("");
  const check = useMutation({
    mutationFn: () =>
      api.get<AuthCheck>(`/settings/deliverability${domain.trim() ? `?domain=${encodeURIComponent(domain.trim())}` : ""}`),
    onError: (e: any) => toast.error(e.message || "Check failed"),
  });
  const r = check.data;
  const chip = (ok: boolean | null | undefined, label: string, extra?: string | null) => (
    <Badge variant={ok === true ? "success" : ok === false ? "danger" : "default"}>
      {label}{ok === true ? " ✓" : ok === false ? " ✗" : " ?"}{extra ? ` (${extra})` : ""}
    </Badge>
  );
  return (
    <Card>
      <CardHeader>
        <CardTitle>Email deliverability preflight</CardTitle>
        <CardDescription>
          SPF / DKIM / DMARC / MX check of your sending domain — Gmail &amp; Yahoo hard-enforce
          these for bulk senders (since Nov 2025). Leave blank to check your configured Gmail address.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2 max-w-md">
          <Input value={domain} onChange={(e) => setDomain(e.target.value)}
                 placeholder="yourdomain.com (optional)" />
          <Button onClick={() => check.mutate()} disabled={check.isPending}>
            {check.isPending ? "Checking…" : "Check"}
          </Button>
        </div>
        {r && (
          <div className="space-y-2">
            <div className="flex flex-wrap items-center gap-2">
              <Badge variant={r.verdict === "pass" ? "success" : r.verdict === "partial" ? "warn" : "danger"}>
                {r.domain}: {r.verdict.toUpperCase()}
              </Badge>
              {chip(r.spf.found, "SPF")}
              {chip(r.dkim.found, "DKIM", r.dkim.selector)}
              {chip(r.dmarc.found, "DMARC", r.dmarc.policy)}
              {chip(r.mx, "MX")}
            </div>
            {r.notes.map((n, i) => (
              <p key={i} className="text-xs text-muted-foreground">• {n}</p>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
