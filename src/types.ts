export type AutomationMode =
  | "recommend_only"
  | "review_in_browser"
  | "guided_apply";

export type SearchSessionStatus =
  | "draft"
  | "running"
  | "blocked"
  | "ready"
  | "failed"
  | "cancelled";

export type ApplicationAttemptStatus =
  | "queued"
  | "running"
  | "prepared"
  | "needs_verification"
  | "blocked"
  | "failed"
  | "cancelled";

export interface CandidateProfile {
  id: number | null;
  full_name: string;
  headline: string;
  summary: string;
  target_roles: string[];
  preferred_cities: string[];
  salary_floor: number;
  years_experience: number;
  degree: string;
  skills: string[];
  must_have_keywords: string[];
  source_filename?: string | null;
  source_language: string;
  updated_at?: string | null;
}

export interface PlatformCapability {
  platform: string;
  label: string;
  search_supported: boolean;
  detail_parse_supported: boolean;
  review_open_supported: boolean;
  guided_apply_supported: boolean;
  session_supported: boolean;
  session_required: boolean;
  selectable: boolean;
  disabled_reason?: string | null;
  rule_pack_version: string;
}

export interface PlatformSession {
  platform: string;
  active: boolean;
  search_ready?: boolean;
  last_started_at?: string | null;
  storage_dir: string;
  recommended_account_notice: string;
}

export interface SearchSession {
  id: string;
  requested_platforms: string[];
  mode: AutomationMode;
  status: SearchSessionStatus;
  job_targets: string[];
  cities: string[];
  salary_floor: number;
  must_have_keywords: string[];
  created_at: string;
  updated_at: string;
  blocked_reason?: string | null;
  summary?: string | null;
  analysis_provider: string;
  analysis_degraded: boolean;
  analysis_notice?: string | null;
}

export interface JobMatch {
  id: string;
  job_id: string;
  platform: string;
  external_job_id: string;
  title: string;
  company_name: string;
  city: string;
  salary_text: string;
  experience_text: string;
  degree_text: string;
  work_mode: string;
  url: string;
  detail_url?: string | null;
  apply_url?: string | null;
  source_company_url?: string | null;
  apply_requires_login: boolean;
  apply_supported: boolean;
  jd_text: string;
  jd_excerpt: string;
  rule_score: number;
  llm_score?: number | null;
  final_score: number;
  highlights: string[];
  missing_keywords: string[];
  risk_flags: string[];
  llm_summary?: string | null;
  cached_llm: boolean;
  analysis_provider: string;
  analysis_degraded: boolean;
  analysis_notice?: string | null;
}

export interface ApplicationAttempt {
  id: string;
  job_id: string;
  platform: string;
  mode: AutomationMode;
  status: ApplicationAttemptStatus;
  created_at: string;
  updated_at: string;
  message: string;
  verification_url?: string | null;
  launch_url?: string | null;
  context: Record<string, unknown>;
}

export interface RiskConsent {
  id: number;
  consent_type: string;
  platform?: string | null;
  version: string;
  accepted_at: string;
}

export interface RiskStatus {
  platform: string;
  emergency_stop_active: boolean;
  cooldown_until?: string | null;
  remaining_hourly: number;
  remaining_daily: number;
  recent_risk_events: number;
}

export interface AppState {
  launch_disclaimer_required: boolean;
  guided_apply_consents: string[];
  emergency_stop_active: boolean;
}

export interface RuntimeConfig {
  api_port: number;
  llm_provider: string;
  llm_effective_provider: string;
  llm_configured: boolean;
  llm_missing_envs: string[];
  llm_notice: string;
  openai_api_key_configured: boolean;
  openai_api_key_preview?: string | null;
  openai_base_url?: string | null;
  openai_model?: string | null;
  official_source_file: string;
}

export interface RuntimeConfigUpdatePayload {
  llm_provider: string;
  openai_base_url?: string | null;
  openai_model?: string | null;
  openai_api_key?: string | null;
  replace_api_key?: boolean;
}

export interface LLMRuntimeProbePayload {
  llm_provider: string;
  openai_base_url?: string | null;
  openai_model?: string | null;
  openai_api_key?: string | null;
  use_saved_api_key?: boolean;
}

export interface LLMConnectionTestResult {
  ok: boolean;
  provider: string;
  model?: string | null;
  latency_ms?: number | null;
  reply_preview?: string | null;
  message: string;
}

export interface LLMModelListResult {
  provider: string;
  models: string[];
  message: string;
}

export interface SearchEvent {
  type: string;
  session_id: string;
  message: string;
  timestamp: string;
  payload?: Record<string, unknown>;
}

export interface VerificationWindowPayload {
  url: string;
  title: string;
  message: string;
}
