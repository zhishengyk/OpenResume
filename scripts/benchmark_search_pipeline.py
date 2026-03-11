from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import shutil
import statistics
import sys
import tempfile
import time


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Benchmark the search pipeline with mock jobs.")
    parser.add_argument("--draft-count", type=int, default=200)
    parser.add_argument("--llm-delay", type=float, default=0.8)
    parser.add_argument("--runs", type=int, default=3)
    return parser.parse_args()


def configure_import_paths(storage_dir: Path) -> None:
    repo_root = Path(__file__).resolve().parents[1]
    backend_root = repo_root / "backend"
    if str(backend_root) not in sys.path:
        sys.path.insert(0, str(backend_root))

    import os

    os.environ.setdefault("OPENRESUME_DISABLE_BROWSER_OPEN", "1")
    os.environ["OPENRESUME_STORAGE_DIR"] = str(storage_dir)


def wait_for_session_status(client, session_id: str, expected: str, timeout: float = 15.0):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        response = client.get(f"/api/search-sessions/{session_id}")
        response.raise_for_status()
        latest = response.json()
        if latest["status"] == expected:
            return latest
        time.sleep(0.05)
    raise RuntimeError(f"session {session_id} did not reach status={expected}: {latest}")


def wait_for_analysis_status(
    client,
    session_id: str,
    expected: str,
    timeout: float = 15.0,
):
    deadline = time.time() + timeout
    latest = None
    while time.time() < deadline:
        response = client.get(f"/api/search-sessions/{session_id}")
        response.raise_for_status()
        latest = response.json()
        if latest["analysis_status"] == expected:
            return latest
        time.sleep(0.05)
    raise RuntimeError(
        f"session {session_id} did not reach analysis_status={expected}: {latest}"
    )


@dataclass
class RunMetrics:
    run_index: int
    time_to_ready_ms: int
    time_to_llm_enriched_ms: int
    fetch_ms: int
    rule_rank_ms: int
    persist_ms: int
    llm_ms: int


def print_summary(values: list[int], label: str) -> None:
    print(
        f"{label}: avg={statistics.mean(values):.1f}ms median={statistics.median(values):.1f}ms"
    )


@contextmanager
def patched_pipeline(draft_count: int, llm_delay: float):
    from openresume_api.adapters.base import NormalizedJobDraft
    from openresume_api.adapters.official import official_adapter
    from openresume_api.services.llm import AnalysisBatch, AnalysisMetadata, LLMResult, llm_service

    original_search_jobs = official_adapter.search_jobs
    original_analyze_jobs = llm_service.analyze_jobs

    def sample_drafts(run_index: int) -> list[NormalizedJobDraft]:
        drafts: list[NormalizedJobDraft] = []
        for index in range(draft_count):
            job_id = f"run-{run_index:02d}-job-{index:04d}"
            drafts.append(
                NormalizedJobDraft(
                    source_company="ByteDance",
                    source_site="jobs.bytedance.com",
                    job_id=job_id,
                    title=f"Frontend Engineer {index}",
                    department="Engineering",
                    employment_type="Experienced",
                    location_raw="Shanghai",
                    location_city="Shanghai",
                    location_country="China",
                    remote_type="onsite",
                    description_html="<p>React TypeScript FastAPI</p>",
                    description_text="React TypeScript FastAPI",
                    requirements_text="React TypeScript",
                    skills_extracted=["React", "TypeScript"],
                    posted_at=datetime(2026, 3, 1),
                    apply_url=(
                        "https://jobs.bytedance.com/experienced/position/"
                        f"{job_id}/detail"
                    ),
                    salary_raw="25K-35K",
                    salary_min=25000,
                    salary_max=35000,
                    lang="zh-CN",
                    crawl_time=datetime(2026, 3, 10),
                    raw_payload={"source": "benchmark", "platform": "official"},
                )
            )
        return drafts

    state = {"run_index": 0}

    async def fake_search_jobs(search, profile):
        return sample_drafts(state["run_index"])

    async def fake_analyze_jobs(db, profile, jobs):
        await asyncio.sleep(llm_delay)
        job_list = list(jobs)
        return AnalysisBatch(
            metadata=AnalysisMetadata(
                provider="heuristic",
                degraded=True,
                notice="benchmark",
            ),
            results=[
                LLMResult(
                    cache_key=f"cache-{job.job_id}",
                    job_id=job.job_id,
                    llm_score=80.0,
                    highlights=["React"],
                    missing_keywords=[],
                    risk_flags=[],
                    llm_summary="benchmark",
                )
                for job in job_list
            ],
        )

    official_adapter.search_jobs = fake_search_jobs
    llm_service.analyze_jobs = fake_analyze_jobs
    try:
        yield state
    finally:
        official_adapter.search_jobs = original_search_jobs
        llm_service.analyze_jobs = original_analyze_jobs


def main() -> None:
    args = parse_args()
    tmpdir = Path(tempfile.mkdtemp(prefix="openresume-bench-"))
    try:
        storage_dir = tmpdir
        configure_import_paths(storage_dir)

        from fastapi.testclient import TestClient
        from sqlmodel import SQLModel, Session, create_engine

        import openresume_api.db as db_module
        from openresume_api.db import get_session
        from openresume_api.main import app
        from openresume_api.models import AppSetting
        from openresume_api.services.search import search_service

        engine = create_engine(
            f"sqlite:///{storage_dir / 'benchmark.db'}",
            connect_args={"check_same_thread": False},
        )
        db_module.engine = engine
        SQLModel.metadata.drop_all(engine)
        SQLModel.metadata.create_all(engine)

        def override_get_session():
            with Session(engine) as session:
                yield session

        app.dependency_overrides[get_session] = override_get_session

        metrics: list[RunMetrics] = []
        with patched_pipeline(args.draft_count, args.llm_delay) as state:
            with TestClient(app) as client:
                client.put(
                    "/api/profile",
                    json={
                        "id": 1,
                        "full_name": "Benchmark Candidate",
                        "headline": "Senior Frontend Engineer",
                        "summary": "React and TypeScript engineer",
                        "target_roles": ["Frontend Engineer", "Full Stack Engineer"],
                        "preferred_cities": ["Shanghai", "Hangzhou"],
                        "salary_floor": 25000,
                        "years_experience": 5,
                        "degree": "Bachelor",
                        "skills": ["React", "TypeScript", "Node.js", "FastAPI"],
                        "must_have_keywords": ["React", "TypeScript"],
                        "tech_stack": ["React", "TypeScript", "Node.js"],
                        "project_experiences": [],
                        "awards": [],
                        "source_filename": "resume.pdf",
                        "source_language": "zh-CN",
                        "raw_text": "React TypeScript resume",
                    },
                ).raise_for_status()

                for run_index in range(1, args.runs + 1):
                    state["run_index"] = run_index
                    response = client.post(
                        "/api/search-sessions",
                        json={
                            "platforms": ["official"],
                            "mode": "recommend_only",
                            "job_targets": ["Frontend Engineer", "Full Stack Engineer"],
                            "cities": ["Shanghai"],
                            "salary_floor": 25000,
                            "must_have_keywords": ["React", "TypeScript"],
                            "source_variants": [],
                            "source_companies": [],
                            "force_refresh": True,
                        },
                    )
                    response.raise_for_status()
                    session_id = response.json()["id"]

                    wait_for_session_status(client, session_id, "ready")
                    wait_for_analysis_status(client, session_id, "ready")

                    with Session(engine) as db:
                        setting = db.get(AppSetting, search_service._session_meta_key(session_id))
                        if not setting:
                            raise RuntimeError(f"missing metrics for session {session_id}")
                        meta = dict(setting.value or {})

                    run_metrics = RunMetrics(
                        run_index=run_index,
                        time_to_ready_ms=int(meta.get("time_to_ready_ms") or 0),
                        time_to_llm_enriched_ms=int(
                            meta.get("time_to_llm_enriched_ms") or 0
                        ),
                        fetch_ms=int(meta.get("fetch_ms") or 0),
                        rule_rank_ms=int(meta.get("rule_rank_ms") or 0),
                        persist_ms=int(meta.get("persist_ms") or 0),
                        llm_ms=int(meta.get("llm_ms") or 0),
                    )
                    metrics.append(run_metrics)
                    print(
                        f"run={run_metrics.run_index} "
                        f"time_to_ready_ms={run_metrics.time_to_ready_ms} "
                        f"time_to_llm_enriched_ms={run_metrics.time_to_llm_enriched_ms} "
                        f"fetch_ms={run_metrics.fetch_ms} "
                        f"rule_rank_ms={run_metrics.rule_rank_ms} "
                        f"persist_ms={run_metrics.persist_ms} "
                        f"llm_ms={run_metrics.llm_ms}"
                    )

        print_summary([item.time_to_ready_ms for item in metrics], "time_to_ready_ms")
        print_summary(
            [item.time_to_llm_enriched_ms for item in metrics],
            "time_to_llm_enriched_ms",
        )
        engine.dispose()
        app.dependency_overrides.pop(get_session, None)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    main()
