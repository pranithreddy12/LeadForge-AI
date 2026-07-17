// Wire-level types mirroring the FastAPI Pydantic schemas. Kept narrow and trustworthy.

export type ID = string;

export interface Page<T> {
  items: T[];
  page: number;
  page_size: number;
  total: number;
  has_next: boolean;
}

export interface Project {
  id: ID;
  name: string;
  business_description: string;
  target_offering?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ICP {
  id: ID;
  project_id: ID;
  name: string;
  summary?: string | null;
  industries: string[];
  countries: string[];
  employee_min?: number | null;
  employee_max?: number | null;
  revenue_min_usd?: number | null;
  revenue_max_usd?: number | null;
  buyer_personas: string[];
  buying_signals: string[];
  keywords: string[];
  excluded_keywords: string[];
  tech_stack_required: string[];
  tech_stack_excluded: string[];
  weights: Record<string, number>;
  is_active: boolean;
  created_at: string;
}

export type PipelineStage =
  | "new" | "qualified" | "contacted" | "replied"
  | "meeting" | "proposal" | "won" | "lost";

export interface Company {
  id: ID;
  name: string;
  domain?: string | null;
  website?: string | null;
  linkedin_url?: string | null;
  industry?: string | null;
  sub_industries: string[];
  employee_count?: number | null;
  employee_range?: string | null;
  revenue_usd?: number | null;
  revenue_range?: string | null;
  country?: string | null;
  city?: string | null;
  region?: string | null;
  founded_year?: number | null;
  tech_stack: string[];
  description?: string | null;
  pipeline_stage: PipelineStage;
  enriched: boolean;
  source?: string | null;
  icp_id?: ID | null;
  funding_total_usd?: number | null;
  last_funding_stage?: string | null;
  score?: number | null;
  grade?: "A+" | "A" | "B" | "C" | "D" | "F" | null;
  created_at: string;
  updated_at: string;
}

export interface RunLead {
  company_id: ID;
  company_name: string;
  city?: string | null;
  score?: number | null;
  grade?: string | null;
  signals: string[];
  qualification_label?: string | null;
  filter_passed: boolean;
  outreach_channel?: string | null;
  outreach_status?: string | null;
  suppression_reason?: string | null;
}

export interface TodayLead {
  draft_id: ID;
  company_id: ID;
  company_name: string;
  domain?: string | null;
  score?: number | null;
  grade?: string | null;
  signal?: string | null;
  subject: string;
  body: string;
  to?: string | null;
  phone?: string | null;
  decision_maker?: string | null;
  email_mx_ok?: boolean | null;
  spam_flags?: string[];
  dm?: string | null;
  dm_ar?: string | null;
  auto_reply_comeback?: string | null;
  edited?: boolean;
  wa_link?: string | null;
  ig_handle?: string | null;
  ig_dm_link?: string | null;
  ig_profile?: string | null;
  socials?: Record<string, string>;
}

export interface PipelineLead {
  company_id: ID;
  company_name: string;
  sent_days_ago: number;
  replied: boolean;
  followups_ready: Array<{
    draft_id: ID; step: number; day?: number | null;
    subject: string; body: string; to?: string | null;
  }>;
}

export interface ManualLogItem {
  id: ID;
  company_name: string;
  channel: string;
  action: string;
  skip_reason?: string | null;
  sent_by_me: boolean;
  replied: boolean;
  notes?: string | null;
  at?: string | null;
}

export interface ReplyLead {
  company_id: ID;
  company_name: string;
  city?: string | null;
  score?: number | null;
  grade?: string | null;
  stage: string;
  channel: string;
  original_message?: string | null;
  reply_text?: string | null;
  reply_at?: string | null;
  suggested_response?: string | null;
}

export interface WorkflowRun {
  id: ID;
  workflow_id: ID;
  status: string;
  started_at?: string | null;
  finished_at?: string | null;
  error?: string | null;
  items_in: number;
  items_out: number;
  step_results: Array<{ id: string; type: string; result: Record<string, unknown> }>;
  run_leads: RunLead[];
  created_at: string;
}

export interface Contact {
  id: ID;
  company_id: ID;
  name: string;
  title?: string | null;
  seniority?: string | null;
  department?: string | null;
  influence_score: number;
  buying_power?: "decision_maker" | "influencer" | "gatekeeper" | "evaluator" | "end_user" | null;
  email?: string | null;
  email_status?: "valid" | "risky" | "invalid" | "unknown" | null;
  email_confidence?: number | null;
  linkedin_url?: string | null;
  phone?: string | null;
  is_primary: boolean;
  tags: string[];
  created_at: string;
}

export type SignalKind =
  | "hiring" | "funding" | "growth" | "product_launch" | "tech_install"
  | "leadership_change" | "partnership" | "news" | "traffic_growth" | "office_expansion";

export interface Signal {
  id: ID;
  company_id: ID;
  kind: SignalKind;
  label: string;
  description?: string | null;
  severity: number;
  confidence: number;
  url?: string | null;
  source?: string | null;
  observed_at?: string | null;
  created_at: string;
}

export interface LeadScore {
  id: ID;
  company_id: ID;
  icp_id?: ID | null;
  score: number;
  grade: "A+" | "A" | "B" | "C" | "D" | "F";
  probability: number;
  fit_score: number;
  funding_score: number;
  hiring_score: number;
  growth_score: number;
  tech_match_score: number;
  email_score: number;
  activity_score: number;
  reasoning: string[];
  suggested_offer?: string | null;
  suggested_contact_title?: string | null;
  pain_points: string[];
  created_at: string;
}

export interface KPI {
  label: string;
  value: number | null;   // null = no basis to compute -> rendered "—"
  delta_pct?: number | null;
  trend?: number[];
}

export interface DashboardSummary {
  leads_found: KPI;
  qualified_leads: KPI;
  avg_score: KPI;
  conversion_rate: KPI;
  revenue: KPI;
}

export interface AccountResearch {
  id: ID;
  company_id: ID;
  summary?: string | null;
  pain_points: string[];
  current_initiatives: string[];
  growth_signals: string[];
  key_facts: string[];
  recommended_pitch?: string | null;
  suggested_contact_title?: string | null;
  confidence: number;
  sources: { title?: string; url?: string; kind?: string }[];
  created_at: string;
}

export interface OpportunityCard {
  company_id: ID;
  company_name: string;
  domain?: string | null;
  industry?: string | null;
  pipeline_stage: PipelineStage;
  score: number;
  grade: "A+" | "A" | "B" | "C" | "D" | "F";
  probability: number;
  why_now: string[];
  pain_points: string[];
  suggested_contact_title?: string | null;
  suggested_offer?: string | null;
  signal_count: number;
  top_signal_kinds: string[];
  scored_at?: string | null;
}

export interface OpportunityStats {
  total_scored: number;
  hot: number;
  warm: number;
  cold: number;
  avg_score: number;
}

export interface Workflow {
  id: ID;
  name: string;
  description?: string | null;
  enabled: boolean;
  schedule: string;
  next_run_at?: string | null;
  last_run_at?: string | null;
  steps: Array<{ id: string; type: string; config: Record<string, unknown>; next: string[] }>;
  settings: Record<string, unknown>;
  created_at: string;
}
