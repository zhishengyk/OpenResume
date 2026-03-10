from __future__ import annotations

from dataclasses import dataclass
import re

from ..adapters.base import NormalizedJobDraft
from ..career_collectors.normalization import normalize_city
from ..models import CandidateProfile


@dataclass
class RuleMatch:
    draft: NormalizedJobDraft
    rule_score: float
    highlights: list[str]
    missing_keywords: list[str]
    risk_flags: list[str]


class MatchingService:
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
            combined_text = "\n".join(
                [draft.title, draft.description_text, draft.requirements_text]
            )
            lowered = combined_text.lower()

            if not self._city_matches(draft.location_city or draft.location_raw, cities):
                continue
            if salary_floor and draft.salary_min and draft.salary_min < salary_floor:
                continue
            if not self._target_matches(
                combined_text, requested_targets or profile.target_roles
            ):
                continue

            matched_keywords = [
                original
                for lowered_skill, original in profile_skills.items()
                if lowered_skill in lowered
            ]
            missing_keywords = [
                keyword
                for keyword in requested_keywords or profile.must_have_keywords
                if keyword.lower() not in lowered
            ]
            if must_have and len(missing_keywords) >= len(must_have):
                continue

            skill_component = min(35.0, len(matched_keywords) * 7.0)
            role_component = 25.0 if any(target in lowered for target in targets) else 10.0
            salary_component = (
                10.0 if draft.salary_min and draft.salary_min >= salary_floor else 5.0
            )
            location_component = (
                8.0
                if self._city_matches(draft.location_city or draft.location_raw, cities)
                else 2.0
            )
            freshness_component = 12.0 if draft.posted_at else 6.0
            requirement_component = 10.0 if draft.requirements_text else 5.0
            score = (
                skill_component
                + role_component
                + salary_component
                + location_component
                + freshness_component
                + requirement_component
            )

            risk_flags: list[str] = []
            if draft.remote_type.lower() == "onsite":
                risk_flags.append("需要现场办公")
            if "leader" in lowered or "team lead" in lowered:
                risk_flags.append("可能包含管理职责")
            if profile.years_experience < 3 and re.search(
                r"(3-5\s*years|3\+\s*years|\u4e09\u5e74\u4ee5\u4e0a|\d+\s*-\s*\d+\s*\u5e74)",
                combined_text,
                re.IGNORECASE,
            ):
                risk_flags.append("经验要求可能偏高")

            matches.append(
                RuleMatch(
                    draft=draft,
                    rule_score=max(score, 0.0),
                    highlights=matched_keywords[:5],
                    missing_keywords=missing_keywords[:4],
                    risk_flags=risk_flags,
                )
            )

        matches.sort(key=lambda item: item.rule_score, reverse=True)
        return matches


matching_service = MatchingService()
