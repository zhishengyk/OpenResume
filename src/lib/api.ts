import type {
  AppState,
  ApplicationAttempt,
  CandidateProfile,
  JobMatch,
  PlatformCapability,
  PlatformSession,
  RiskConsent,
  RiskStatus,
  SearchSession,
} from "../types";

declare global {
  interface Window {
    openResumeDesktop?: {
      apiBaseUrl?: string;
      openExternal?: (url: string) => void;
    };
  }
}

const API_BASE =
  window.openResumeDesktop?.apiBaseUrl || "http://127.0.0.1:38417";

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
    // Ignore JSON parse errors and use the raw response text instead.
  }

  return detail;
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;

  try {
    response = await fetch(`${API_BASE}${path}`, init);
  } catch (error) {
    const message =
      error instanceof Error && error.message
        ? error.message
        : "unknown network error";
    throw new Error(
      `本地接口连接失败，请确认 OpenResume 后端仍在运行。原始错误: ${message}`,
    );
  }

  if (!response.ok) {
    const detail = await response.text();
    throw new Error(extractErrorMessage(detail));
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}

export const apiBaseUrl = API_BASE;

export const api = {
  getAppState: () => request<AppState>("/api/app-state"),
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
    platform: string;
    mode: string;
    job_targets: string[];
    cities: string[];
    salary_floor: number;
    must_have_keywords: string[];
  }) =>
    request<SearchSession>("/api/search-sessions", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }),
  listSearchSessions: () => request<SearchSession[]>("/api/search-sessions"),
  getSearchSession: (id: string) =>
    request<SearchSession>(`/api/search-sessions/${id}`),
  retrySearchSession: (id: string) =>
    request<SearchSession>(`/api/search-sessions/${id}/retry`, {
      method: "POST",
    }),
  openSearchVerification: (id: string) =>
    request<{ message: string }>(
      `/api/search-sessions/${id}/open-verification`,
      {
        method: "POST",
      },
    ),
  getSearchMatches: (id: string) =>
    request<JobMatch[]>(`/api/search-sessions/${id}/matches`),
  openReview: (jobId: string) =>
    request<{ message: string }>(`/api/jobs/${jobId}/open-review`, {
      method: "POST",
    }),
  guidedApply: (jobId: string) =>
    request<ApplicationAttempt>(`/api/jobs/${jobId}/guided-apply`, {
      method: "POST",
    }),
  listAttempts: () =>
    request<ApplicationAttempt[]>("/api/application-attempts"),
  cancelAttempt: (attemptId: string) =>
    request<ApplicationAttempt>(
      `/api/application-attempts/${attemptId}/cancel`,
      {
        method: "POST",
      },
    ),
  setEmergencyStop: (active: boolean) =>
    request<{ active: boolean }>("/api/emergency-stop", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active }),
    }),
};
