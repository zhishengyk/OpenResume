#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
from collections import Counter
from pathlib import Path
import re
import sys
from urllib.parse import urlparse


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run live smoke tests against OpenResume official career-site extractors."
    )
    parser.add_argument("--repo", required=True, help="Path to the OpenResume repo root.")
    parser.add_argument(
        "--input-file",
        help="Optional file containing lines such as 'Company: https://careers.example.com/'.",
    )
    parser.add_argument(
        "--source",
        action="append",
        default=[],
        help="Inline source in the form 'Company=https://careers.example.com/'. Repeatable.",
    )
    parser.add_argument(
        "--job-target",
        action="append",
        default=[],
        help="Target role used for extraction and relevance checks. Repeatable.",
    )
    parser.add_argument(
        "--city",
        action="append",
        default=[],
        help="Preferred city. Repeatable.",
    )
    parser.add_argument(
        "--detail-limit",
        type=int,
        default=5,
        help="Maximum number of detail pages to fetch per source after list extraction.",
    )
    parser.add_argument(
        "--years-experience",
        type=int,
        default=0,
        help="Candidate profile years of experience.",
    )
    return parser.parse_args()


def parse_source_line(line: str) -> tuple[str, str] | None:
    if "http://" not in line and "https://" not in line:
        return None
    match = re.search(r"https?://\S+", line)
    if not match:
        return None
    url = match.group(0).strip().rstrip(")")
    prefix = line[: match.start()].strip()
    company = re.sub(r"[:=\s]+$", "", prefix).strip()
    if not company:
        company = urlparse(url).netloc
    return company, url


def parse_sources(input_file: str | None, inline_sources: list[str]) -> list[tuple[str, str]]:
    parsed: list[tuple[str, str]] = []
    seen: set[str] = set()

    if input_file:
        for raw_line in Path(input_file).read_text(encoding="utf-8", errors="ignore").splitlines():
            item = parse_source_line(raw_line)
            if not item:
                continue
            if item[1] in seen:
                continue
            seen.add(item[1])
            parsed.append(item)

    for raw in inline_sources:
        item = parse_source_line(raw)
        if not item:
            raise SystemExit(f"Invalid --source value: {raw}")
        if item[1] in seen:
            continue
        seen.add(item[1])
        parsed.append(item)

    if not parsed:
        raise SystemExit("No sources were provided.")
    return parsed


def load_repo_modules(repo_root: Path):
    backend_path = repo_root / "backend"
    if not backend_path.exists():
        raise SystemExit(f"Backend path not found: {backend_path}")
    sys.path.insert(0, str(backend_path))

    from openresume_api.adapters.official import OfficialAdapter
    from openresume_api.models import CandidateProfile
    from openresume_api.schemas import SearchSessionCreate
    from openresume_api.services.official_sources import OfficialSource, _classify_source

    return OfficialAdapter, CandidateProfile, SearchSessionCreate, OfficialSource, _classify_source


async def inspect_source(
    adapter,
    source,
    search,
    profile,
    detail_limit: int,
):
    from openresume_api.config import settings
    import httpx

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/123.0.0.0 Safari/537.36"
        )
    }
    report = {
        "company": source.company_name,
        "url": source.url,
        "source_kind": source.source_kind,
    }

    async with httpx.AsyncClient(
        timeout=settings.official_request_timeout_seconds,
        headers=headers,
    ) as client:
        try:
            result = await adapter._source_candidates(client, source, search)
        except Exception as exc:
            report["status"] = "fetch_error"
            report["error"] = f"{type(exc).__name__}: {exc}"
            return report

        report["status"] = "ok"
        report["extractor"] = result.extractor
        report["entry_url"] = result.entry_url
        report["candidate_count"] = len(result.candidates)

        filtered_candidates = []
        hard_filter_counts: Counter[str] = Counter()
        for candidate in result.candidates:
            reasons = candidate.raw_payload.get("hard_filter_reasons") or []
            if reasons:
                hard_filter_counts.update(reasons)
                continue
            filtered_candidates.append(candidate)

        report["hard_filtered"] = len(result.candidates) - len(filtered_candidates)
        report["entry_candidates"] = len(filtered_candidates)
        report["hard_filter_top"] = [
            {"reason": reason, "count": count}
            for reason, count in hard_filter_counts.most_common(5)
        ]

        detail_candidates = filtered_candidates[:detail_limit]
        report["detail_checked"] = len(detail_candidates)

        enriched = await asyncio.gather(
            *[
                adapter._enrich_candidate(
                    client,
                    source,
                    candidate,
                    search.job_targets,
                    search.cities,
                )
                for candidate in detail_candidates
            ],
            return_exceptions=True,
        )

        detail_errors = []
        detail_dropped = 0
        final_drafts = []
        quality_penalized = 0

        for item in enriched:
            if isinstance(item, Exception):
                detail_errors.append(f"{type(item).__name__}: {item}")
                continue
            if item is None:
                detail_dropped += 1
                continue
            quality = (item.raw_payload or {}).get("quality") or {}
            score = int(quality.get("score") or 0)
            if 60 <= score < 80:
                quality_penalized += 1
            final_drafts.append(
                {
                    "title": item.title,
                    "city": item.city,
                    "detail_url": item.detail_url,
                    "quality_score": score,
                }
            )

        report["detail_dropped"] = detail_dropped
        report["detail_errors"] = detail_errors[:3]
        report["quality_penalized"] = quality_penalized
        report["final_drafts"] = len(final_drafts)
        report["sample_jobs"] = final_drafts[:3]

        if report["candidate_count"] == 0:
            report["status"] = "zero_candidates"
        elif report["entry_candidates"] == 0:
            report["status"] = "hard_filtered"
        elif report["final_drafts"] == 0:
            report["status"] = "zero_final"

        return report


def print_report(report: dict) -> None:
    print(report["company"])
    print(f"  url: {report['url']}")
    print(f"  source_kind: {report['source_kind']}")
    print(f"  status: {report['status']}")
    if report.get("error"):
        print(f"  error: {report['error']}")
        return
    print(f"  extractor: {report.get('extractor', '-')}")
    print(f"  entry_url: {report.get('entry_url', '-')}")
    print(f"  candidate_count: {report.get('candidate_count', 0)}")
    print(f"  hard_filtered: {report.get('hard_filtered', 0)}")
    print(f"  entry_candidates: {report.get('entry_candidates', 0)}")
    print(f"  detail_checked: {report.get('detail_checked', 0)}")
    print(f"  detail_dropped: {report.get('detail_dropped', 0)}")
    print(f"  quality_penalized: {report.get('quality_penalized', 0)}")
    print(f"  final_drafts: {report.get('final_drafts', 0)}")
    for item in report.get("hard_filter_top", []):
        print(f"  hard_filter: {item['reason']} x{item['count']}")
    for item in report.get("detail_errors", []):
        print(f"  detail_error: {item}")
    for item in report.get("sample_jobs", []):
        print(
            "  sample_job: "
            f"{item['title']} | {item['city']} | quality={item['quality_score']} | {item['detail_url']}"
        )


async def main() -> int:
    args = parse_args()
    repo_root = Path(args.repo).resolve()
    (
        OfficialAdapter,
        CandidateProfile,
        SearchSessionCreate,
        OfficialSource,
        classify_source,
    ) = load_repo_modules(repo_root)

    targets = args.job_target or [
        "软件开发工程师",
        "后端开发工程师",
        "算法工程师",
    ]
    cities = args.city or []
    search = SearchSessionCreate(
        platforms=["official"],
        mode="manual",
        job_targets=targets,
        cities=cities,
        salary_floor=0,
        must_have_keywords=[],
    )
    profile = CandidateProfile(
        target_roles=targets,
        preferred_cities=cities,
        years_experience=args.years_experience,
    )
    adapter = OfficialAdapter()

    parsed_sources = parse_sources(args.input_file, args.source)
    reports = []
    for company, url in parsed_sources:
        source = OfficialSource(
            company_name=company,
            url=url,
            host=urlparse(url).netloc.lower().lstrip("www."),
            source_kind=classify_source(url),
        )
        reports.append(await inspect_source(adapter, source, search, profile, args.detail_limit))

    ok_sites = sum(1 for report in reports if report.get("final_drafts", 0) > 0)
    print(f"summary: {ok_sites}/{len(reports)} sources produced usable jobs")
    for report in reports:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
