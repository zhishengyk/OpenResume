import type {
  AppState,
  ApplicationAttempt,
  CandidateProfile,
  JobMatch,
  LLMConnectionTestResult,
  LLMModelListResult,
  LLMRuntimeProbePayload,
  PlatformCapability,
  PlatformSession,
  RiskConsent,
  RiskStatus,
  RuntimeConfig,
  RuntimeConfigUpdatePayload,
  SearchSession,
  SourceInfo,
  VerificationWindowPayload,
} from "../types";

declare global {
  interface Window {
    openResumeDesktop?: {
      apiBaseUrl?: string;
      openExternal?: (url: string) => Promise<unknown>;
      openVerificationWindow?: (
        url: string,
        title?: string,
      ) => Promise<{ closed: boolean }>;
    };
  }
}

const API_BASE = window.openResumeDesktop?.apiBaseUrl || "http://127.0.0.1:38417";

function extractErrorMessage(detail: string): string {
  if (!detail) {
    return "请求失败";
  }

  try {
    const payload = JSON.parse(detail) as { detail?: string };
    if (typeof payload.detail === "string" && payload.detail.trim()) {
      return payload.detail;
    }
  } catch {
    // Ignore parse failures and return the raw body.
  }

  return detail;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch (error) {
    const message =
      error instanceof Error && error.message ? error.message : "未知网络错误";
    throw new Error(
      `本地 API 不可用，请确认 OpenResume 后端已经启动。根因：${message}`,
    );
  }

  if (!response.ok) {
    throw new Error(extractErrorMessage(await response.text()));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const apiBaseUrl = API_BASE;

export const api = {
  getAppState: () => request<AppState>("/api/app-state"),
  getRuntimeConfig: () => request<RuntimeConfig>("/api/runtime-config"),
  updateRuntimeConfig: (payload: RuntimeConfigUpdatePayload) =>
    request<RuntimeConfig>("/api/runtime-config", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listRuntimeModels: (payload: LLMRuntimeProbePayload) =>
    request<LLMModelListResult>("/api/runtime-config/llm/models", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  testRuntimeLLM: (payload: LLMRuntimeProbePayload) =>
    request<LLMConnectionTestResult>("/api/runtime-config/llm/test", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  acceptDisclaimer: () =>
    request<RiskConsent>("/api/risk-consents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        consent_type: "launch_disclaimer",
        version: "1.0.0",
      }),
    }),
  uploadResume: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return request<CandidateProfile>("/api/resume/upload", {
      method: "POST",
      body: formData,
    });
  },
  getProfile: () => request<CandidateProfile>("/api/profile"),
  updateProfile: (payload: CandidateProfile) =>
    request<CandidateProfile>("/api/profile", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getPlatforms: () => request<PlatformCapability[]>("/api/platforms"),
  getPlatformCapabilities: (platform: string) =>
    request<PlatformCapability>(`/api/platforms/${platform}/capabilities`),
  startPlatformSession: (platform: string) =>
    request<PlatformSession>(`/api/platforms/${platform}/session/start`, {
      method: "POST",
    }),
  getPlatformSession: (platform: string) =>
    request<PlatformSession>(`/api/platforms/${platform}/session`),
  checkPlatformSessionReady: (platform: string) =>
    request<PlatformSession>(`/api/platforms/${platform}/session/check-ready`, {
      method: "POST",
    }),
  createGuidedApplyConsent: (platform: string) =>
    request<RiskConsent>("/api/risk-consents", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        consent_type: "guided_apply",
        platform,
        version: "1.0.0",
      }),
    }),
  getRiskStatus: (platform: string) =>
    request<RiskStatus>(`/api/platforms/${platform}/risk-status`),
  createSearchSession: (payload: {
    platforms: string[];
    mode: string;
    job_targets: string[];
    cities: string[];
    salary_floor: number;
    must_have_keywords: string[];
    source_variants?: string[];
    source_companies?: string[];
    match_limit?: number;
    company_job_limit?: number;
    force_refresh?: boolean;
  }) =>
    request<SearchSession>("/api/search-sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  getSources: () => request<SourceInfo[]>("/api/sources"),
  getSourceVariants: () => request<string[]>("/api/sources/variants"),
  getSourceCompanies: () => request<string[]>("/api/sources/companies"),
  listSearchSessions: () => request<SearchSession[]>("/api/search-sessions"),
  getSearchSession: (id: string) => request<SearchSession>(`/api/search-sessions/${id}`),
  retrySearchSession: (id: string) =>
    request<SearchSession>(`/api/search-sessions/${id}/retry`, {
      method: "POST",
    }),
  openSearchVerification: (id: string) =>
    request<VerificationWindowPayload>(`/api/search-sessions/${id}/open-verification`, {
      method: "POST",
    }),
  getSearchMatches: (id: string) =>
    request<JobMatch[]>(`/api/search-sessions/${id}/matches`),
  openReview: (listingId: string) =>
    request<{ message: string }>(`/api/jobs/${listingId}/open-review`, {
      method: "POST",
    }),
  guidedApply: (listingId: string) =>
    request<ApplicationAttempt>(`/api/jobs/${listingId}/guided-apply`, {
      method: "POST",
    }),
  listAttempts: () => request<ApplicationAttempt[]>("/api/application-attempts"),
  getAttempt: (attemptId: string) =>
    request<ApplicationAttempt>(`/api/application-attempts/${attemptId}`),
  openAttemptVerificationWindow: (attemptId: string) =>
    request<VerificationWindowPayload>(
      `/api/application-attempts/${attemptId}/open-verification-window`,
      { method: "POST" },
    ),
  continueAttempt: (attemptId: string) =>
    request<ApplicationAttempt>(`/api/application-attempts/${attemptId}/continue`, {
      method: "POST",
    }),
  cancelAttempt: (attemptId: string) =>
    request<ApplicationAttempt>(`/api/application-attempts/${attemptId}/cancel`, {
      method: "POST",
    }),
  setEmergencyStop: (active: boolean) =>
    request<{ active: boolean }>("/api/emergency-stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    }),
};
