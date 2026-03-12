export type AutomationMode =
  | "recommend_only"
  | "review_in_browser"
  | "guided_apply";

export type ApplyExecutionMode = "semi_auto" | "auto_submit";

export type SearchSessionStatus =
  | "draft"
  | "running"
  | "blocked"
  | "ready"
  | "failed"
  | "cancelled";

export type SearchAnalysisStatus =
  | "pending"
  | "running"
  | "ready"
  | "failed";

export type ApplicationAttemptStatus =
  | "queued"
  | "running"
  | "prepared"
  | "submitted"
  | "needs_verification"
  | "blocked"
  | "failed"
  | "cancelled";

export type ApplyBatchStatus =
  | "queued"
  | "running"
  | "prepared"
  | "submitted"
  | "needs_verification"
  | "failed"
  | "cancelled";

export interface ProjectExperience {
  name: string;
  role: string;
  summary: string;
  technologies: string[];
}

export interface Award {
  title: string;
  issuer: string;
  year: string;
  summary: string;
}

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
  tech_stack: string[];
  project_experiences: ProjectExperience[];
  awards: Award[];
  source_filename?: string | null;
  source_language: string;
  raw_text: string;
  profile_signature?: string | null;
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
  source_variants: string[];
  source_companies: string[];
  match_limit: number;
  company_job_limit: number;
  force_refresh: boolean;
  created_at: string;
  updated_at: string;
  blocked_reason?: string | null;
  summary?: string | null;
  analysis_status: SearchAnalysisStatus;
  analysis_provider: string;
  analysis_degraded: boolean;
  analysis_notice?: string | null;
}

export interface JobLocationOption {
  listing_id: string;
  location_city: string;
  location_raw: string;
  apply_url: string;
}

export interface JobMatch {
  id: string;
  listing_id: string;
  platform: string;
  job_id: string;
  source_company: string;
  source_site: string;
  title: string;
  department: string;
  employment_type: string;
  location_raw: string;
  location_city: string;
  location_country: string;
  remote_type: string;
  description_html: string;
  description_text: string;
  requirements_text: string;
  skills_extracted: string[];
  posted_at?: string | null;
  apply_url: string;
  location_display: string;
  location_cities: string[];
  location_options: JobLocationOption[];
  is_merged: boolean;
  merged_count: number;
  salary_raw: string;
  salary_min?: number | null;
  salary_max?: number | null;
  lang: string;
  crawl_time: string;
  apply_supported: boolean;
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
  listing_id: string;
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

export interface OfficialSite {
  company_key: string;
  company_name: string;
  label: string;
  login_url: string;
  source_sites: string[];
  supported_variants: string[];
  supports_auto_submit: boolean;
}

export interface OfficialSessionCache {
  account_id: string;
  company_key: string;
  storage_state_path: string;
  status: string;
  expires_at?: string | null;
  last_success_at?: string | null;
  last_verified_at?: string | null;
  created_at: string;
  updated_at: string;
}

export interface OfficialAccount {
  id: string;
  company_key: string;
  company_name: string;
  display_name: string;
  username: string;
  has_credentials: boolean;
  is_default: boolean;
  status: string;
  is_logged_in: boolean;
  last_test_message?: string | null;
  last_tested_at?: string | null;
  last_verified_at?: string | null;
  created_at: string;
  updated_at: string;
  session_cache?: OfficialSessionCache | null;
}

export interface ResumeAsset {
  id: string;
  label: string;
  source_filename: string;
  storage_path: string;
  mime_type: string;
  file_size: number;
  content_hash: string;
  created_at: string;
  updated_at: string;
}

export interface CompanyBinding {
  company_key: string;
  default_resume_asset_id?: string | null;
  updated_at: string;
}

export interface ApplyBatchItem {
  id: string;
  batch_id: string;
  listing_id: string;
  company_key: string;
  account_id?: string | null;
  resume_asset_id?: string | null;
  execution_mode: ApplyExecutionMode;
  status: ApplyBatchStatus;
  message: string;
  verification_url?: string | null;
  launch_url?: string | null;
  context: Record<string, unknown>;
  created_at: string;
  updated_at: string;
}

export interface ApplyBatch {
  id: string;
  session_id?: string | null;
  platform: string;
  execution_mode: ApplyExecutionMode;
  status: ApplyBatchStatus;
  message: string;
  total_items: number;
  completed_items: number;
  submitted_items: number;
  created_at: string;
  updated_at: string;
  items: ApplyBatchItem[];
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
  official_sources_summary: string;
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

export interface SourceInfo {
  key: string;
  company_name: string;
  variant: string;
  label: string;
}
