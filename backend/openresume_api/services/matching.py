from __future__ import annotations

from dataclasses import dataclass

from ..adapters.base import NormalizedJobDraft
from ..adapters.official_extractors.common import (
    candidate_quality_penalty,
    matches_requested_targets,
    normalize_city,
    unrelated_role_reasons,
)
from ..models import CandidateProfile


@dataclass
class RuleMatch:
    draft: NormalizedJobDraft
    rule_score: float
    highlights: list[str]
    missing_keywords: list[str]
    risk_flags: list[str]


class MatchingService:
    def _city_matches(self, draft_city: str, requested_cities: set[str]) -> bool:
        if not requested_cities:
            return True
        normalized_draft = normalize_city(draft_city)
        return normalized_draft in requested_cities

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
        targets = [target.lower() for target in requested_targets or profile.target_roles]
        cities = {
            normalize_city(city)
            for city in (requested_cities or profile.preferred_cities)
            if city.strip()
        }
        must_have = [
            keyword.lower()
            for keyword in requested_keywords or profile.must_have_keywords
        ]
        profile_skills = {skill.lower(): skill for skill in profile.skills}

        for draft in drafts:
            quality = draft.raw_payload.get("quality") or {}
            quality_score = int(quality.get("score") or 100)
            if quality_score < 60:
                continue
            if not self._city_matches(draft.city, cities):
                continue
            if salary_floor and draft.salary_min and draft.salary_min < salary_floor:
                continue
            combined_text = f"{draft.title} {draft.jd_text}"
            if targets and not matches_requested_targets(combined_text, requested_targets or profile.target_roles):
                continue
            role_reasons = unrelated_role_reasons(
                draft.title,
                draft.jd_text[:400],
                requested_targets or profile.target_roles,
            )
            if role_reasons:
                continue

            matched_keywords = [
                original
                for lowered, original in profile_skills.items()
                if lowered in draft.jd_text.lower()
            ]
            missing_keywords = [
                keyword
                for keyword in requested_keywords or profile.must_have_keywords
                if keyword.lower() not in draft.jd_text.lower()
            ]

            if must_have and len(missing_keywords) >= len(must_have):
                continue

            skill_component = min(35.0, len(matched_keywords) * 7.0)
            role_component = (
                25.0 if any(target in draft.title.lower() for target in targets) else 12.0
            )
            level_component = (
                15.0
                if any(keyword in draft.title for keyword in ["\u9ad8\u7ea7", "\u8d44\u6df1"])
                else 9.0
            )
            domain_component = (
                10.0
                if any(keyword in draft.jd_text for keyword in ["AI", "\u4e2d\u540e\u53f0"])
                else 5.0
            )
            salary_component = 10.0 if draft.salary_min >= salary_floor else 5.0
            location_component = 5.0 if self._city_matches(draft.city, cities) else 2.0
            score = (
                skill_component
                + role_component
                + level_component
                + domain_component
                + salary_component
                + location_component
            )
            score -= candidate_quality_penalty(draft.raw_payload)
            score = max(score, 0.0)

            risk_flags: list[str] = []
            if draft.work_mode.lower() == "onsite":
                risk_flags.append("\u9700\u8981\u5750\u73ed")
            if "leader" in draft.jd_text.lower() or "\u5e26\u56e2\u961f" in draft.jd_text:
                risk_flags.append("\u8981\u6c42\u5e26\u56e2\u961f")
            if "\u0033-\u0035\u5e74" in draft.experience_text and profile.years_experience < 3:
                risk_flags.append("\u5e74\u9650\u53ef\u80fd\u4e0d\u8db3")
            quality_penalty = candidate_quality_penalty(draft.raw_payload)
            if quality_penalty:
                risk_flags.append("官网信息质量一般")

            matches.append(
                RuleMatch(
                    draft=draft,
                    rule_score=score,
                    highlights=matched_keywords[:5],
                    missing_keywords=missing_keywords[:4],
                    risk_flags=risk_flags,
                )
            )

        matches.sort(key=lambda item: item.rule_score, reverse=True)
        return matches


matching_service = MatchingService()
