from __future__ import annotations

from dataclasses import dataclass

from ..adapters.base import NormalizedJobDraft
from ..models import CandidateProfile


@dataclass
class RuleMatch:
    draft: NormalizedJobDraft
    rule_score: float
    highlights: list[str]
    missing_keywords: list[str]
    risk_flags: list[str]


class MatchingService:
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
        cities = set(requested_cities or profile.preferred_cities)
        must_have = [
            keyword.lower()
            for keyword in requested_keywords or profile.must_have_keywords
        ]
        profile_skills = {skill.lower(): skill for skill in profile.skills}

        for draft in drafts:
            if cities and draft.city not in cities:
                continue
            if salary_floor and draft.salary_min and draft.salary_min < salary_floor:
                continue
            if not any(
                target in draft.title.lower() or target in draft.jd_text.lower()
                for target in targets
            ):
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
            level_component = 15.0 if "高级" in draft.title or "资深" in draft.title else 9.0
            domain_component = 10.0 if "AI" in draft.jd_text or "中后台" in draft.jd_text else 5.0
            salary_component = 10.0 if draft.salary_min >= salary_floor else 5.0
            location_component = 5.0 if draft.city in cities else 2.0
            score = (
                skill_component
                + role_component
                + level_component
                + domain_component
                + salary_component
                + location_component
            )

            risk_flags = []
            if draft.work_mode.lower() == "onsite":
                risk_flags.append("需要坐班")
            if "leader" in draft.jd_text.lower() or "带团队" in draft.jd_text:
                risk_flags.append("要求带团队")
            if "3-5年" in draft.experience_text and profile.years_experience < 3:
                risk_flags.append("年限可能不足")

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

