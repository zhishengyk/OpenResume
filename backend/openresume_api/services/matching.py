from __future__ import annotations

from dataclasses import dataclass
import re

from ..adapters.base import NormalizedJobDraft
from ..career_collectors.normalization import normalize_city
from ..models import CandidateProfile
from .profile import profile_service


@dataclass
class RuleMatch:
    draft: NormalizedJobDraft
    rule_score: float
    highlights: list[str]
    missing_keywords: list[str]
    risk_flags: list[str]


class MatchingService:
    @staticmethod
    def _matched_terms(terms: list[str], lowered_text: str) -> list[str]:
        matched: list[str] = []
        for term in terms:
            normalized = term.lower().strip()
            if normalized and normalized in lowered_text:
                matched.append(term)
        return list(dict.fromkeys(matched))

    def _city_matches(self, location_city: str, requested_cities: set[str]) -> bool:
        if not requested_cities:
            return True
        normalized = normalize_city(location_city)
        return normalized in requested_cities

    def _target_matches(self, text: str, targets: list[str]) -> bool:
        if not targets:
            return True
        lowered = text.lower()
        return any(target.lower() in lowered for target in targets)

    def filter_and_score(
        self,
        profile: CandidateProfile,
        drafts: list[NormalizedJobDraft],
        requested_targets: list[str],
        requested_cities: list[str],
        requested_keywords: list[str],
        salary_floor: int,
    ) -> list[RuleMatch]:
        matches: list[RuleMatch] = []
        active_targets = requested_targets or profile.target_roles
        targets = [target.lower() for target in active_targets]
        cities = {
            normalize_city(city)
            for city in (requested_cities or profile.preferred_cities)
            if city.strip()
        }
        must_have = [
            keyword.lower()
            for keyword in requested_keywords or profile.must_have_keywords
        ]
        project_terms = profile_service.project_evidence_terms(profile)
        award_terms = profile_service.award_evidence_terms(profile)

        for draft in drafts:
            combined_text = "\n".join(
                [draft.title, draft.description_text, draft.requirements_text]
            )
            lowered = combined_text.lower()
            location_text = draft.location_city or draft.location_raw
            city_match = self._city_matches(location_text, cities)
            salary_known = draft.salary_min is not None
            salary_match = (
                not salary_floor
                or not salary_known
                or bool(draft.salary_min and draft.salary_min >= salary_floor)
            )
            target_match = self._target_matches(combined_text, active_targets)

            matched_skill_terms = self._matched_terms(profile.skills, lowered)
            matched_tech_terms = self._matched_terms(profile.tech_stack, lowered)
            matched_project_terms = self._matched_terms(project_terms, lowered)
            matched_award_terms = self._matched_terms(award_terms, lowered)

            highlights = list(
                dict.fromkeys(
                    matched_tech_terms[:4]
                    + matched_skill_terms[:4]
                    + matched_project_terms[:3]
                    + matched_award_terms[:2]
                )
            )
            missing_keywords = [
                keyword
                for keyword in requested_keywords or profile.must_have_keywords
                if keyword.lower() not in lowered
            ]
            if not missing_keywords and profile.tech_stack:
                missing_keywords.extend(
                    [
                        keyword
                        for keyword in profile.tech_stack
                        if keyword.lower() not in lowered
                    ][:2]
                )

            tech_component = min(26.0, len(matched_tech_terms) * 8.0)
            skill_component = min(18.0, len(matched_skill_terms) * 4.0)
            project_component = min(14.0, len(matched_project_terms) * 4.0)
            award_component = min(8.0, len(matched_award_terms) * 3.0)
            role_component = 22.0 if target_match else (10.0 if not targets else 3.0)
            salary_component = (
                8.0
                if salary_floor and salary_match
                else 5.0
                if not salary_floor
                else 3.0
                if not salary_known
                else 1.0
            )
            location_component = 6.0 if city_match else (4.0 if not cities else 1.0)
            freshness_component = 8.0 if draft.posted_at else 4.0
            requirement_component = 6.0 if draft.requirements_text else 3.0
            base_score = (
                tech_component
                + skill_component
                + project_component
                + award_component
                + role_component
                + salary_component
                + location_component
                + freshness_component
                + requirement_component
            )

            penalty = 0.0
            if cities and not city_match:
                penalty += 12.0
            if salary_floor and not salary_match:
                penalty += 10.0
            if targets and not target_match:
                penalty += 18.0
            if must_have:
                missing_ratio = len(missing_keywords) / max(1, len(must_have))
                penalty += min(18.0, missing_ratio * 18.0)

            score = max(base_score - penalty, 0.0)
            risk_flags: list[str] = []
            if cities and not city_match:
                risk_flags.append("City preference mismatch")
            if salary_floor and salary_known and not salary_match:
                risk_flags.append("Salary below floor")
            if targets and not target_match:
                risk_flags.append("Role keyword match is weak")
            if must_have and len(missing_keywords) >= max(1, (len(must_have) + 1) // 2):
                risk_flags.append("Many required keywords missing")
            if profile.tech_stack and not matched_tech_terms:
                risk_flags.append("Limited tech stack overlap")
            if profile.project_experiences and not matched_project_terms:
                risk_flags.append("No clear project evidence overlap")
            if draft.remote_type.lower() == "onsite":
                risk_flags.append("Onsite work required")
            if "leader" in lowered or "team lead" in lowered:
                risk_flags.append("May include people management")
            if profile.years_experience < 3 and re.search(
                r"(3-5\s*years|3\+\s*years|\u4e09\u5e74\u4ee5\u4e0a|\d+\s*-\s*\d+\s*\u5e74)",
                combined_text,
                re.IGNORECASE,
            ):
                risk_flags.append("Experience requirement may be high")

            matches.append(
                RuleMatch(
                    draft=draft,
                    rule_score=score,
                    highlights=highlights[:6],
                    missing_keywords=missing_keywords[:4],
                    risk_flags=risk_flags,
                )
            )

        matches.sort(key=lambda item: item.rule_score, reverse=True)
        return matches


matching_service = MatchingService()
