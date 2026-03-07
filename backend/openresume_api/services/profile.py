from __future__ import annotations

from pathlib import Path
import re
from typing import Iterable

from docx import Document
from pypdf import PdfReader
from sqlmodel import Session

from ..config import settings
from ..models import CandidateProfile, now_utc
from ..schemas import CandidateProfileUpdate

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
]

COMMON_CITIES = [
    "上海",
    "杭州",
    "北京",
    "深圳",
    "广州",
    "苏州",
    "成都",
]


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _read_docx(path: Path) -> str:
    document = Document(str(path))
    return "\n".join(paragraph.text for paragraph in document.paragraphs)


def _extract_first_line(lines: Iterable[str]) -> str:
    for line in lines:
        cleaned = line.strip()
        if cleaned and len(cleaned) <= 32:
            return cleaned
    return ""


def _extract_roles(text: str) -> list[str]:
    matches = re.findall(
        r"(前端工程师|全栈工程师|后端工程师|产品经理|测试工程师|算法工程师)",
        text,
    )
    unique = list(dict.fromkeys(matches))
    return unique[:3] or ["前端工程师", "全栈工程师"]


def _extract_skills(text: str) -> list[str]:
    return [skill for skill in COMMON_SKILLS if skill.lower() in text.lower()]


def _extract_cities(text: str) -> list[str]:
    return [city for city in COMMON_CITIES if city in text]


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

    def parse_resume(self, filename: str, content: bytes) -> CandidateProfileUpdate:
        extension = Path(filename).suffix.lower()
        output_path = settings.resume_dir / filename
        output_path.write_bytes(content)

        if extension == ".pdf":
            raw_text = _read_pdf(output_path)
        elif extension == ".docx":
            raw_text = _read_docx(output_path)
        else:
            raise ValueError("当前仅支持 PDF 和 DOCX 简历文件。")

        lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
        name = _extract_first_line(lines)
        skills = _extract_skills(raw_text)
        roles = _extract_roles(raw_text)
        cities = _extract_cities(raw_text)
        summary = "\n".join(lines[1:4]) if len(lines) > 1 else ""

        return CandidateProfileUpdate(
            id=1,
            full_name=name,
            headline=roles[0] if roles else "",
            summary=summary,
            target_roles=roles,
            preferred_cities=cities,
            salary_floor=25000 if "高级" in raw_text or "资深" in raw_text else 18000,
            years_experience=5 if "5年" in raw_text or "五年" in raw_text else 3,
            degree="本科" if "本科" in raw_text else "",
            skills=skills,
            must_have_keywords=skills[:5],
            source_filename=filename,
            source_language="zh-CN" if re.search(r"[\u4e00-\u9fff]", raw_text) else "en",
        )

    def save_profile(self, db: Session, update: CandidateProfileUpdate) -> CandidateProfile:
        profile = self.load_or_create(db)
        for field, value in update.model_dump().items():
            if field == "id" or field == "updated_at":
                continue
            setattr(profile, field, value)

        profile.updated_at = update.updated_at or now_utc()
        db.add(profile)
        db.commit()
        db.refresh(profile)
        return profile


profile_service = ProfileService()

