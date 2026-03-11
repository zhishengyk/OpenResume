from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any, Iterable

import httpx
from docx import Document
from pypdf import PdfReader
from sqlmodel import Session

from ..config import settings
from ..models import CandidateProfile, now_utc
from ..schemas import AwardItem, CandidateProfileUpdate, ProjectExperienceItem
from .runtime_config import runtime_config_service

COMMON_SKILLS = [
    "React",
    "TypeScript",
    "JavaScript",
    "Node.js",
    "Python",
    "FastAPI",
    "Vue",
    "Next.js",
    "Electron",
    "SQL",
    "MySQL",
    "PostgreSQL",
    "Redis",
    "Docker",
    "Playwright",
    "HTML",
    "CSS",
    "Tailwind CSS",
    "Nuxt.js",
    "Express",
    "MongoDB",
    "Kubernetes",
    "AWS",
    "Azure",
    "GCP",
    "GraphQL",
    "Java",
    "Spring Boot",
    "Go",
    "C++",
    "C#",
]

COMMON_CITIES = [
    "Shanghai",
    "Hangzhou",
    "Beijing",
    "Shenzhen",
    "Guangzhou",
    "Suzhou",
    "Chengdu",
    "上海",
    "杭州",
    "北京",
    "深圳",
    "广州",
    "苏州",
    "成都",
]

TECH_SYNONYMS = {
    "js": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "typescript": "TypeScript",
    "node": "Node.js",
    "nodejs": "Node.js",
    "node.js": "Node.js",
    "reactjs": "React",
    "react.js": "React",
    "vuejs": "Vue",
    "vue.js": "Vue",
    "next": "Next.js",
    "nextjs": "Next.js",
    "next.js": "Next.js",
    "tailwind": "Tailwind CSS",
    "tailwindcss": "Tailwind CSS",
    "postgres": "PostgreSQL",
    "postgresql": "PostgreSQL",
    "golang": "Go",
    "k8s": "Kubernetes",
    "gcp": "GCP",
}

ROLE_PATTERNS = [
    "frontend engineer",
    "front-end engineer",
    "full stack engineer",
    "backend engineer",
    "software engineer",
    "data engineer",
    "product manager",
    "test engineer",
    "qa engineer",
    "machine learning engineer",
    "前端工程师",
    "全栈工程师",
    "后端工程师",
    "产品经理",
    "测试工程师",
    "算法工程师",
]

STOP_PHRASES = {
    "project",
    "projects",
    "award",
    "awards",
    "experience",
    "experiences",
    "skills",
    "stack",
    "technology",
    "technologies",
    "summary",
    "role",
}


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path: Path) -> str:
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _clean_text(value: str, *, max_length: int | None = None) -> str:
    cleaned = re.sub(r"\s+", " ", str(value or "")).strip()
    if max_length is not None:
        return cleaned[:max_length]
    return cleaned


def _extract_first_line(lines: Iterable[str]) -> str:
    for line in lines:
        cleaned = _clean_text(line, max_length=32)
        if cleaned:
            return cleaned
    return ""


def _normalize_skill_name(value: str) -> str:
    cleaned = _clean_text(value, max_length=40)
    if not cleaned:
        return ""
    return TECH_SYNONYMS.get(cleaned.lower(), cleaned)


def _unique_preserve(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    results: list[str] = []
    for value in values:
        key = value.casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        results.append(value)
    return results


def _normalize_string_list(
    values: Iterable[str],
    *,
    limit: int,
    skill_mode: bool = False,
) -> list[str]:
    normalized: list[str] = []
    for value in values:
        item = _normalize_skill_name(value) if skill_mode else _clean_text(value, max_length=60)
        if item:
            normalized.append(item)
    return _unique_preserve(normalized)[:limit]


def _section_header_kind(line: str) -> str | None:
    lowered = _clean_text(line).lower()
    if lowered in {
        "projects",
        "project experience",
        "project experiences",
        "selected projects",
        "项目",
        "项目经历",
        "项目经验",
    }:
        return "project"
    if lowered in {
        "awards",
        "honors",
        "honours",
        "achievements",
        "奖项",
        "荣誉",
        "获奖经历",
        "证书",
    }:
        return "award"
    return None


def _extract_roles(text: str) -> list[str]:
    lowered = text.lower()
    matches: list[str] = []
    for pattern in ROLE_PATTERNS:
        index = lowered.find(pattern.lower())
        if index == -1:
            continue
        matches.append(_clean_text(text[index : index + len(pattern)], max_length=40))
    results = _unique_preserve(matches)
    if results:
        return results[:3]
    return ["前端工程师", "全栈工程师"]


def _extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    matches = [skill for skill in COMMON_SKILLS if skill.lower() in lowered]
    matches.extend(re.findall(r"[A-Za-z][A-Za-z0-9.+#/ -]{1,24}", text))
    return _normalize_string_list(matches, limit=20, skill_mode=True)


def _extract_cities(text: str) -> list[str]:
    lowered = text.lower()
    return _normalize_string_list(
        [city for city in COMMON_CITIES if city.lower() in lowered],
        limit=6,
    )


def _extract_signal_phrases(text: str, *, limit: int) -> list[str]:
    phrases: list[str] = []
    for piece in re.split(r"[\n,，;；/|、]", text):
        cleaned = _clean_text(piece, max_length=48)
        lowered = cleaned.lower()
        if (
            len(cleaned) < 2
            or lowered in STOP_PHRASES
            or re.fullmatch(r"[\W_]+", cleaned)
        ):
            continue
        phrases.append(cleaned)
    return _unique_preserve(phrases)[:limit]


def _project_from_block(block: list[str]) -> dict[str, Any] | None:
    if not block:
        return None
    first = re.sub(r"^[\-\u2022*\d.)\s]+", "", block[0]).strip()
    first = re.sub(r"^(project|项目)[:：-]?\s*", "", first, flags=re.IGNORECASE)
    role = ""
    summary_parts: list[str] = []
    for line in block[1:]:
        stripped = _clean_text(line, max_length=140)
        if not stripped:
            continue
        if re.match(r"^(role|职责|岗位|职位|担任)[:：-]?", stripped, re.IGNORECASE):
            role = re.sub(
                r"^(role|职责|岗位|职位|担任)[:：-]?\s*",
                "",
                stripped,
                flags=re.IGNORECASE,
            )
            continue
        summary_parts.append(stripped)
    summary = _clean_text(" ".join(summary_parts), max_length=220)
    if not first and not summary:
        return None
    return {
        "name": _clean_text(first, max_length=80),
        "role": _clean_text(role, max_length=60),
        "summary": summary,
        "technologies": _extract_skills(" ".join(block))[:8],
    }


def _award_from_block(block: list[str]) -> dict[str, Any] | None:
    if not block:
        return None
    first = re.sub(r"^[\-\u2022*\d.)\s]+", "", block[0]).strip()
    title = re.sub(
        r"^(award|awards|honor|honour|achievement|奖项|荣誉|获奖)[:：-]?\s*",
        "",
        first,
        flags=re.IGNORECASE,
    )
    issuer = ""
    summary_parts: list[str] = []
    for line in block[1:]:
        stripped = _clean_text(line, max_length=140)
        if not stripped:
            continue
        if re.match(r"^(issuer|颁发|主办|机构)[:：-]?", stripped, re.IGNORECASE):
            issuer = re.sub(
                r"^(issuer|颁发|主办|机构)[:：-]?\s*",
                "",
                stripped,
                flags=re.IGNORECASE,
            )
            continue
        summary_parts.append(stripped)
    combined = " ".join(block)
    year_match = re.search(r"(20\d{2}|19\d{2})", combined)
    if not title and not summary_parts:
        return None
    return {
        "title": _clean_text(title, max_length=80),
        "issuer": _clean_text(issuer, max_length=60),
        "year": year_match.group(1) if year_match else "",
        "summary": _clean_text(" ".join(summary_parts), max_length=180),
    }


def _section_blocks(lines: list[str], kind: str) -> list[list[str]]:
    blocks: list[list[str]] = []
    active = False
    current: list[str] = []
    for line in lines:
        header_kind = _section_header_kind(line)
        if header_kind is not None:
            if active and current:
                blocks.append(current)
                current = []
            active = header_kind == kind
            continue
        if not active:
            continue
        stripped = _clean_text(line, max_length=140)
        if not stripped:
            if current:
                blocks.append(current)
                current = []
            continue
        if current and len(current) >= 4:
            looks_like_new_block = (
                len(stripped) <= 80
                and not re.match(
                    r"^(role|职责|岗位|职位|担任|issuer|颁发|主办|机构)[:：-]?",
                    stripped,
                    re.IGNORECASE,
                )
            )
            if looks_like_new_block:
                blocks.append(current)
                current = [stripped]
                continue
        current.append(stripped)
    if current:
        blocks.append(current)
    return blocks


def _extract_project_experiences(raw_text: str) -> list[dict[str, Any]]:
    lines = [line.rstrip() for line in raw_text.splitlines()]
    blocks = _section_blocks(lines, "project")
    projects = [_project_from_block(block) for block in blocks]
    normalized_lines = [_clean_text(line, max_length=140) for line in lines if _clean_text(line)]
    for index, line in enumerate(normalized_lines):
        if not re.search(r"(project|项目)", line, re.IGNORECASE):
            continue
        projects.append(_project_from_block([line] + normalized_lines[index + 1 : index + 3]))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in projects:
        if not item:
            continue
        key = (
            str(item.get("name", "")).casefold(),
            str(item.get("summary", "")).casefold(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:6]


def _extract_awards(raw_text: str) -> list[dict[str, Any]]:
    lines = [line.rstrip() for line in raw_text.splitlines()]
    blocks = _section_blocks(lines, "award")
    awards = [_award_from_block(block) for block in blocks]
    normalized_lines = [_clean_text(line, max_length=140) for line in lines if _clean_text(line)]
    for index, line in enumerate(normalized_lines):
        if not re.search(r"(award|honor|honour|achievement|奖项|荣誉|获奖)", line, re.IGNORECASE):
            continue
        awards.append(_award_from_block([line] + normalized_lines[index + 1 : index + 2]))
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in awards:
        if not item:
            continue
        key = (
            str(item.get("title", "")).casefold(),
            str(item.get("issuer", "")).casefold(),
            str(item.get("year", "")),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:6]


def _normalize_project_experiences(
    values: Iterable[ProjectExperienceItem | dict[str, Any]],
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for item in values:
        payload = item.model_dump() if isinstance(item, ProjectExperienceItem) else dict(item)
        name = _clean_text(payload.get("name", ""), max_length=80)
        role = _clean_text(payload.get("role", ""), max_length=60)
        summary = _clean_text(payload.get("summary", ""), max_length=220)
        technologies = _normalize_string_list(
            payload.get("technologies", []),
            limit=8,
            skill_mode=True,
        )
        if not name and not summary:
            continue
        key = (name.casefold(), summary.casefold())
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "name": name,
                "role": role,
                "summary": summary,
                "technologies": technologies,
            }
        )
    return results[:6]


def _normalize_awards(values: Iterable[AwardItem | dict[str, Any]]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in values:
        payload = item.model_dump() if isinstance(item, AwardItem) else dict(item)
        title = _clean_text(payload.get("title", ""), max_length=80)
        issuer = _clean_text(payload.get("issuer", ""), max_length=60)
        year_match = re.search(r"(20\d{2}|19\d{2})", str(payload.get("year", "")))
        year = year_match.group(1) if year_match else ""
        summary = _clean_text(payload.get("summary", ""), max_length=180)
        if not title and not summary:
            continue
        key = (title.casefold(), issuer.casefold(), year)
        if key in seen:
            continue
        seen.add(key)
        results.append(
            {
                "title": title,
                "issuer": issuer,
                "year": year,
                "summary": summary,
            }
        )
    return results[:6]


def _extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("Model response did not contain JSON.")
    return json.loads(text[start : end + 1])


def _signature_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


class ProfileService:
    def load_or_create(self, db: Session) -> CandidateProfile:
        profile = db.get(CandidateProfile, 1)
        if profile:
            return profile

        profile = CandidateProfile(id=1)
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile

    def normalize_update(self, update: CandidateProfileUpdate) -> CandidateProfileUpdate:
        payload = update.model_dump()
        payload["full_name"] = _clean_text(payload.get("full_name", ""), max_length=60)
        payload["headline"] = _clean_text(payload.get("headline", ""), max_length=80)
        payload["summary"] = _clean_text(payload.get("summary", ""), max_length=600)
        payload["target_roles"] = _normalize_string_list(payload.get("target_roles", []), limit=6)
        payload["preferred_cities"] = _normalize_string_list(
            payload.get("preferred_cities", []),
            limit=6,
        )
        payload["skills"] = _normalize_string_list(
            payload.get("skills", []),
            limit=20,
            skill_mode=True,
        )
        payload["must_have_keywords"] = _normalize_string_list(
            payload.get("must_have_keywords", []),
            limit=12,
            skill_mode=True,
        )
        payload["tech_stack"] = _normalize_string_list(
            payload.get("tech_stack", []),
            limit=20,
            skill_mode=True,
        )
        payload["project_experiences"] = _normalize_project_experiences(
            payload.get("project_experiences", [])
        )
        payload["awards"] = _normalize_awards(payload.get("awards", []))
        payload["degree"] = _clean_text(payload.get("degree", ""), max_length=30)
        payload["source_language"] = (
            _clean_text(payload.get("source_language", "") or "zh-CN", max_length=20)
            or "zh-CN"
        )
        payload["source_filename"] = (
            _clean_text(payload.get("source_filename", ""), max_length=260) or None
        )
        payload["raw_text"] = str(payload.get("raw_text", "") or "")[:20000]
        payload["salary_floor"] = max(0, int(payload.get("salary_floor", 0) or 0))
        payload["years_experience"] = max(
            0,
            min(50, int(payload.get("years_experience", 0) or 0)),
        )
        return CandidateProfileUpdate.model_validate(payload)

    def profile_signature(
        self,
        profile: CandidateProfile | CandidateProfileUpdate,
    ) -> str:
        normalized = self.normalize_update(
            CandidateProfileUpdate.model_validate(
                {
                    "id": getattr(profile, "id", 1),
                    "full_name": profile.full_name,
                    "headline": profile.headline,
                    "summary": profile.summary,
                    "target_roles": list(profile.target_roles),
                    "preferred_cities": list(profile.preferred_cities),
                    "salary_floor": profile.salary_floor,
                    "years_experience": profile.years_experience,
                    "degree": profile.degree,
                    "skills": list(profile.skills),
                    "must_have_keywords": list(profile.must_have_keywords),
                    "tech_stack": list(getattr(profile, "tech_stack", [])),
                    "project_experiences": list(
                        getattr(profile, "project_experiences", [])
                    ),
                    "awards": list(getattr(profile, "awards", [])),
                    "source_filename": profile.source_filename,
                    "source_language": profile.source_language,
                    "raw_text": getattr(profile, "raw_text", ""),
                }
            )
        )
        normalized_payload = normalized.model_dump()
        return _signature_json(
            {
                "headline": normalized_payload["headline"],
                "summary": normalized_payload["summary"],
                "target_roles": normalized_payload["target_roles"],
                "preferred_cities": normalized_payload["preferred_cities"],
                "salary_floor": normalized_payload["salary_floor"],
                "years_experience": normalized_payload["years_experience"],
                "degree": normalized_payload["degree"],
                "skills": normalized_payload["skills"],
                "must_have_keywords": normalized_payload["must_have_keywords"],
                "tech_stack": normalized_payload["tech_stack"],
                "project_experiences": normalized_payload["project_experiences"],
                "awards": normalized_payload["awards"],
            }
        )

    def build_search_keyword_basis(
        self,
        requested_targets: list[str],
        profile: CandidateProfile,
    ) -> list[str]:
        primary = _normalize_string_list(requested_targets or profile.target_roles, limit=6)
        supplemental = _normalize_string_list(
            profile.tech_stack or profile.must_have_keywords or profile.skills,
            limit=3,
            skill_mode=True,
        )
        return _unique_preserve(primary + supplemental)[:8]

    def project_evidence_terms(self, profile: CandidateProfile) -> list[str]:
        terms: list[str] = []
        for item in profile.project_experiences:
            payload = dict(item or {})
            terms.extend(payload.get("technologies", []) or [])
            terms.extend(
                _extract_signal_phrases(
                    " ".join(
                        [
                            str(payload.get("name", "")),
                            str(payload.get("role", "")),
                            str(payload.get("summary", "")),
                        ]
                    ),
                    limit=4,
                )
            )
        return _normalize_string_list(terms, limit=12)

    def award_evidence_terms(self, profile: CandidateProfile) -> list[str]:
        terms: list[str] = []
        for item in profile.awards:
            payload = dict(item or {})
            terms.extend(
                _extract_signal_phrases(
                    " ".join(
                        [
                            str(payload.get("title", "")),
                            str(payload.get("issuer", "")),
                            str(payload.get("summary", "")),
                        ]
                    ),
                    limit=3,
                )
            )
        return _normalize_string_list(terms, limit=8)

    def _enhance_profile_fields(
        self,
        update: CandidateProfileUpdate,
    ) -> CandidateProfileUpdate:
        config = runtime_config_service.get_llm_config()
        state = runtime_config_service.llm_runtime_state(config)
        if config.llm_provider != "openai_compatible" or not state.configured:
            return update

        payload = {
            "model": config.openai_model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Extract structured candidate portrait data from resume text. "
                        "Return strict JSON with keys tech_stack, project_experiences, awards. "
                        "project_experiences items must include name, role, summary, technologies. "
                        "awards items must include title, issuer, year, summary. "
                        "Do not invent facts. Prefer empty arrays over guesses."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "raw_text": update.raw_text[:8000],
                            "heuristic": {
                                "tech_stack": update.tech_stack,
                                "project_experiences": update.project_experiences,
                                "awards": update.awards,
                            },
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
            "temperature": 0.1,
        }
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {config.openai_api_key}",
        }
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{config.openai_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
            )
            response.raise_for_status()
            content = (
                response.json().get("choices", [{}])[0].get("message", {}).get("content", "")
            )
        parsed = _extract_json_object(str(content))
        merged = update.model_copy(
            update={
                "tech_stack": parsed.get("tech_stack", update.tech_stack),
                "project_experiences": parsed.get(
                    "project_experiences",
                    update.project_experiences,
                ),
                "awards": parsed.get("awards", update.awards),
            }
        )
        return self.normalize_update(merged)

    def parse_resume(self, filename: str, content: bytes) -> CandidateProfileUpdate:
        extension = Path(filename).suffix.lower()
        output_path = settings.resume_dir / filename
        output_path.write_bytes(content)

        if extension == ".pdf":
            raw_text = _read_pdf(output_path)
        elif extension == ".docx":
            raw_text = _read_docx(output_path)
        else:
            raise ValueError("Only PDF and DOCX resumes are supported.")

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        skills = _extract_skills(raw_text)
        heuristic = CandidateProfileUpdate(
            id=1,
            full_name=_extract_first_line(lines),
            headline=_extract_roles(raw_text)[0] if raw_text else "",
            summary="\n".join(lines[1:4]) if len(lines) > 1 else "",
            target_roles=_extract_roles(raw_text),
            preferred_cities=_extract_cities(raw_text),
            salary_floor=25000
            if re.search(r"(senior|高级|资深)", raw_text, re.IGNORECASE)
            else 18000,
            years_experience=5
            if re.search(r"(5\s*\+?\s*years|5年|五年)", raw_text, re.IGNORECASE)
            else 3,
            degree="本科" if "本科" in raw_text else "",
            skills=skills,
            must_have_keywords=skills[:5],
            tech_stack=skills[:20],
            project_experiences=_extract_project_experiences(raw_text),
            awards=_extract_awards(raw_text),
            source_filename=filename,
            source_language="zh-CN" if re.search(r"[\u4e00-\u9fff]", raw_text) else "en",
            raw_text=raw_text,
        )
        normalized = self.normalize_update(heuristic)
        try:
            return self._enhance_profile_fields(normalized)
        except Exception:
            return normalized

    def save_profile(self, db: Session, update: CandidateProfileUpdate) -> CandidateProfile:
        normalized = self.normalize_update(update)
        profile = self.load_or_create(db)
        for field, value in normalized.model_dump().items():
            if field in {"id", "updated_at"}:
                continue
            setattr(profile, field, value)

        profile.updated_at = normalized.updated_at or now_utc()
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile


profile_service = ProfileService()
