import type { Award, CandidateProfile, ProjectExperience } from "../types";
import { splitCommaValues } from "./utils";

export const SEARCH_DRAFT_STORAGE_KEY = "openresume.search.profileDraft";
export const SEARCH_DRAFT_VERSION = 2;

export interface SearchProfileDraftFields {
  jobTargets: string;
  cities: string;
  salaryFloor: string;
  mustHaveKeywords: string;
  matchLimit: string;
  companyJobLimit: string;
  techStack: string;
  projectExperiences: string;
  awards: string;
}

export interface SearchProfileDraftState {
  version: number;
  profileSignature: string;
  userEdited: boolean;
  fields: SearchProfileDraftFields;
}

export function profileToSearchDraftFields(
  profile: CandidateProfile,
): SearchProfileDraftFields {
  return {
    jobTargets: profile.target_roles.join(", "),
    cities: profile.preferred_cities.join(", "),
    salaryFloor: String(profile.salary_floor || 0),
    mustHaveKeywords: profile.must_have_keywords.join(", "),
    matchLimit: "200",
    companyJobLimit: "200",
    techStack: profile.tech_stack.join(", "),
    projectExperiences: serializeProjectExperiences(profile.project_experiences),
    awards: serializeAwards(profile.awards),
  };
}

export function serializeProjectExperiences(items: ProjectExperience[]): string {
  return items
    .map((item) =>
      [
        item.name.trim(),
        item.role.trim(),
        item.summary.trim(),
        item.technologies.join("/"),
      ]
        .filter(Boolean)
        .join(" | "),
    )
    .filter(Boolean)
    .join("\n");
}

export function serializeAwards(items: Award[]): string {
  return items
    .map((item) =>
      [item.title.trim(), item.issuer.trim(), item.year.trim(), item.summary.trim()]
        .filter(Boolean)
        .join(" | "),
    )
    .filter(Boolean)
    .join("\n");
}

export function parseProjectExperiences(input: string): ProjectExperience[] {
  return input
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [name = "", role = "", summary = "", technologies = ""] = line
        .split("|")
        .map((part) => part.trim());
      return {
        name,
        role,
        summary,
        technologies: splitCommaValues(technologies.replace(/\//g, ",")),
      };
    })
    .filter((item) => item.name || item.summary);
}

export function parseAwards(input: string): Award[] {
  return input
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const [title = "", issuer = "", year = "", summary = ""] = line
        .split("|")
        .map((part) => part.trim());
      return {
        title,
        issuer,
        year,
        summary,
      };
    })
    .filter((item) => item.title || item.summary);
}

export function safeReadSearchDraft(): SearchProfileDraftState | null {
  if (typeof window === "undefined") {
    return null;
  }
  const raw = window.localStorage.getItem(SEARCH_DRAFT_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as SearchProfileDraftState;
    if (
      parsed.version !== SEARCH_DRAFT_VERSION ||
      !parsed.fields ||
      typeof parsed.profileSignature !== "string"
    ) {
      return null;
    }
    return parsed;
  } catch {
    return null;
  }
}

export function writeSearchDraft(state: SearchProfileDraftState) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(SEARCH_DRAFT_STORAGE_KEY, JSON.stringify(state));
}

export function buildProfileUpdateFromDraft(
  profile: CandidateProfile,
  fields: SearchProfileDraftFields,
): CandidateProfile {
  return {
    ...profile,
    tech_stack: splitCommaValues(fields.techStack),
    project_experiences: parseProjectExperiences(fields.projectExperiences),
    awards: parseAwards(fields.awards),
  };
}
