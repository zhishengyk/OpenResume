from __future__ import annotations

import asyncio
from datetime import datetime

from fastapi import HTTPException
from sqlmodel import Session, select

from .. import db as db_module
from ..automation.base import ApplyExecutionRequest, ApplyExecutionOutcome
from ..automation.official_drivers import get_official_driver
from ..automation.playwright_runtime import playwright_automation_runtime
from ..models import ApplyBatch, ApplyBatchItem, CandidateProfile, JobListing
from .official_assets import official_asset_service
from .official_sites import get_official_site, resolve_company_key


FINAL_ITEM_STATUSES = {"prepared", "submitted", "failed", "cancelled"}


class ApplyBatchService:
    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._runtime = playwright_automation_runtime
        self._driver_getter = get_official_driver

    def list_batches(self, db: Session, *, session_id: str | None = None) -> list[ApplyBatch]:
        query = select(ApplyBatch).order_by(ApplyBatch.created_at.desc())
        if session_id:
            query = query.where(ApplyBatch.session_id == session_id)
        return db.exec(query).all()

    def get_batch(self, db: Session, batch_id: str) -> ApplyBatch:
        batch = db.get(ApplyBatch, batch_id)
        if not batch:
            raise HTTPException(status_code=404, detail="Apply batch not found.")
        return batch

    def list_batch_items(self, db: Session, batch_id: str) -> list[ApplyBatchItem]:
        return db.exec(
            select(ApplyBatchItem)
            .where(ApplyBatchItem.batch_id == batch_id)
            .order_by(ApplyBatchItem.created_at.asc())
        ).all()

    async def create_batch(
        self,
        db: Session,
        *,
        listing_ids: list[str],
        execution_mode: str,
        session_id: str | None,
        confirm_auto_submit: bool,
        start_background: bool = True,
    ) -> ApplyBatch:
        normalized_mode = self._normalize_mode(execution_mode)
        if normalized_mode == "auto_submit" and not confirm_auto_submit:
            raise HTTPException(
                status_code=400,
                detail="Auto-submit batches require explicit risk confirmation.",
            )

        jobs = self._resolve_jobs(db, listing_ids)
        normalized_listing_ids = [job.id for job in jobs]
        resolution = self._resolve_assets(db, jobs)

        batch = ApplyBatch(
            session_id=session_id,
            platform="official",
            execution_mode=normalized_mode,
            status="queued",
            message="Apply batch queued.",
            total_items=len(normalized_listing_ids),
            completed_items=0,
            submitted_items=0,
        )
        db.add(batch)
        db.commit()
        db.refresh(batch)

        now = datetime.utcnow()
        for job in jobs:
            company_key = resolution[job.id]["company_key"]
            account = resolution[job.id]["account"]
            resume_asset = resolution[job.id]["resume_asset"]
            db.add(
                ApplyBatchItem(
                    batch_id=batch.id,
                    listing_id=job.id,
                    company_key=company_key,
                    account_id=account.id,
                    resume_asset_id=resume_asset.id,
                    execution_mode=normalized_mode,
                    status="queued",
                    message="Waiting to run.",
                    context={
                        "job_title": job.title,
                        "job_id": job.job_id,
                        "source_company": job.source_company,
                        "source_site": job.source_site,
                        "account_display_name": account.display_name,
                        "resume_label": resume_asset.label,
                    },
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()

        if start_background:
            asyncio.create_task(self._run_batch(batch.id))
        return self.get_batch(db, batch.id)

    async def continue_batch(self, db: Session, batch_id: str) -> ApplyBatch:
        batch = self.get_batch(db, batch_id)
        if batch.status not in {"needs_verification", "failed", "queued", "prepared"}:
            raise HTTPException(status_code=409, detail="This batch cannot be continued.")

        batch.status = "queued"
        batch.message = "Apply batch queued for retry."
        batch.updated_at = datetime.utcnow()
        db.add(batch)

        items = self.list_batch_items(db, batch_id)
        for item in items:
            if item.status in {"needs_verification", "failed"}:
                item.status = "queued"
                item.message = "Queued for retry."
                item.updated_at = datetime.utcnow()
                db.add(item)
        db.commit()

        asyncio.create_task(self._run_batch(batch.id))
        return self.get_batch(db, batch.id)

    def cancel_batch(self, db: Session, batch_id: str) -> ApplyBatch:
        batch = self.get_batch(db, batch_id)
        batch.status = "cancelled"
        batch.message = "Cancelled by user."
        batch.updated_at = datetime.utcnow()
        db.add(batch)

        items = self.list_batch_items(db, batch_id)
        for item in items:
            if item.status in {"queued", "running", "needs_verification", "prepared"}:
                item.status = "cancelled"
                item.message = "Cancelled by user."
                item.updated_at = datetime.utcnow()
                db.add(item)
        db.commit()
        return self.get_batch(db, batch_id)

    async def _run_batch(self, batch_id: str) -> None:
        async with self._lock:
            with Session(db_module.engine) as db:
                batch = db.get(ApplyBatch, batch_id)
                if not batch or batch.status == "cancelled":
                    return
                batch.status = "running"
                batch.message = "Apply batch is running."
                batch.updated_at = datetime.utcnow()
                db.add(batch)
                db.commit()

            while True:
                with Session(db_module.engine) as db:
                    batch = db.get(ApplyBatch, batch_id)
                    if not batch or batch.status == "cancelled":
                        return

                    items = self.list_batch_items(db, batch_id)
                    next_item = next(
                        (
                            item
                            for item in items
                            if item.status in {"queued", "running"}
                        ),
                        None,
                    )
                    if next_item is None:
                        self._refresh_batch_summary(db, batch_id)
                        return

                    next_item.status = "running"
                    next_item.message = "Applying..."
                    next_item.updated_at = datetime.utcnow()
                    db.add(next_item)
                    db.commit()
                    next_item_id = next_item.id

                outcome = await self._execute_item(batch_id=batch_id, item_id=next_item_id)

                with Session(db_module.engine) as db:
                    item = db.get(ApplyBatchItem, next_item_id)
                    batch = db.get(ApplyBatch, batch_id)
                    if not item or not batch:
                        return

                    item.status = outcome.status
                    item.message = outcome.message
                    item.verification_url = outcome.verification_url
                    item.launch_url = outcome.launch_url
                    item.context = {
                        **(item.context or {}),
                        **(outcome.context or {}),
                    }
                    item.updated_at = datetime.utcnow()
                    db.add(item)

                    self._refresh_batch_summary(db, batch_id, commit=False)
                    batch = db.get(ApplyBatch, batch_id)
                    if not batch:
                        return
                    if outcome.status == "needs_verification":
                        batch.status = "needs_verification"
                        batch.message = outcome.message
                    batch.updated_at = datetime.utcnow()
                    db.add(batch)
                    db.commit()

                    if outcome.status == "needs_verification":
                        return

    async def _execute_item(self, *, batch_id: str, item_id: str) -> ApplyExecutionOutcome:
        with Session(db_module.engine) as db:
            item = db.get(ApplyBatchItem, item_id)
            if not item:
                return ApplyExecutionOutcome(status="failed", message="Apply item no longer exists.")

            listing = db.get(JobListing, item.listing_id)
            if not listing:
                return ApplyExecutionOutcome(status="failed", message="Job listing not found.")

            account = official_asset_service.get_account(db, item.account_id or "")
            resume_asset = official_asset_service.get_resume_asset(db, item.resume_asset_id or "")
            cache = official_asset_service.ensure_session_cache(db, account.id)
            profile = db.get(CandidateProfile, 1) or CandidateProfile(id=1)
            site = get_official_site(item.company_key)
            driver = self._driver_getter(item.company_key)

            if not official_asset_service.storage_state_exists(cache):
                message = f"{account.company_name} 当前未登录，请先在账号池完成官网登录。"
                now = datetime.utcnow()
                official_asset_service.mark_session_cache(
                    db,
                    account_id=account.id,
                    status="missing",
                    last_verified_at=now,
                )
                official_asset_service.record_account_test_result(
                    db,
                    account_id=account.id,
                    message=message,
                    tested_at=now,
                )
                return ApplyExecutionOutcome(
                    status="failed",
                    message=message,
                    context={"company_key": item.company_key, "phase": "login"},
                )

            request = ApplyExecutionRequest(
                company_key=item.company_key,
                apply_url=listing.apply_url,
                execution_mode=item.execution_mode,
                full_name=profile.full_name,
                headline=profile.headline,
                resume_path=resume_asset.storage_path,
                storage_state_path=cache.storage_state_path,
            )

        try:
            session_ready, session_message = await self._runtime.inspect(
                storage_state_path=request.storage_state_path,
                headless=True,
                callback=lambda page: driver.check_session(
                    page,
                    target_url=site.session_check_url or site.login_url,
                ),
            )
            now = datetime.utcnow()
            if not session_ready:
                with Session(db_module.engine) as db:
                    official_asset_service.mark_session_cache(
                        db,
                        account_id=item.account_id or "",
                        status="missing",
                        last_verified_at=now,
                    )
                    official_asset_service.record_account_test_result(
                        db,
                        account_id=item.account_id or "",
                        message=session_message,
                        tested_at=now,
                    )
                return ApplyExecutionOutcome(
                    status="failed",
                    message=session_message,
                    context={"company_key": item.company_key, "phase": "login"},
                )

            with Session(db_module.engine) as db:
                official_asset_service.mark_session_cache(
                    db,
                    account_id=item.account_id or "",
                    status="ready",
                    last_success_at=now,
                    last_verified_at=now,
                )

            outcome = await self._runtime.run(
                storage_state_path=request.storage_state_path,
                headless=item.execution_mode == "auto_submit",
                callback=lambda page: driver.run(page, request),
            )
        except Exception as error:
            with Session(db_module.engine) as db:
                official_asset_service.mark_session_cache(
                    db,
                    account_id=item.account_id or "",
                    status="error",
                    last_verified_at=datetime.utcnow(),
                )
                official_asset_service.record_account_test_result(
                    db,
                    account_id=item.account_id or "",
                    message=str(error),
                    tested_at=datetime.utcnow(),
                )
            return ApplyExecutionOutcome(
                status="failed",
                message=str(error),
            )

        with Session(db_module.engine) as db:
            if outcome.status in {"prepared", "submitted"}:
                official_asset_service.mark_session_cache(
                    db,
                    account_id=item.account_id or "",
                    status="ready",
                    last_success_at=datetime.utcnow(),
                    last_verified_at=datetime.utcnow(),
                )
            elif outcome.status == "needs_verification":
                official_asset_service.mark_session_cache(
                    db,
                    account_id=item.account_id or "",
                    status="needs_verification",
                    last_verified_at=datetime.utcnow(),
                )
            elif outcome.status == "failed":
                official_asset_service.mark_session_cache(
                    db,
                    account_id=item.account_id or "",
                    status="missing",
                    last_verified_at=datetime.utcnow(),
                )
            official_asset_service.record_account_test_result(
                db,
                account_id=item.account_id or "",
                message=outcome.message,
                tested_at=datetime.utcnow(),
                verified_at=datetime.utcnow() if outcome.status in {"prepared", "submitted"} else None,
            )

        if outcome.status == "needs_verification" and outcome.verification_url:
            try:
                await self._runtime.interactive_capture(
                    storage_state_path=request.storage_state_path,
                    target_url=outcome.verification_url,
                    timeout_seconds=180,
                )
            except Exception:
                pass
        return outcome

    def _resolve_jobs(self, db: Session, listing_ids: list[str]) -> list[JobListing]:
        normalized_ids = list(dict.fromkeys(item.strip() for item in listing_ids if item.strip()))
        if not normalized_ids:
            raise HTTPException(status_code=400, detail="At least one listing must be selected.")

        jobs = {
            job.id: job
            for job in db.exec(select(JobListing).where(JobListing.id.in_(normalized_ids))).all()
        }
        missing_ids = [listing_id for listing_id in normalized_ids if listing_id not in jobs]
        if missing_ids:
            raise HTTPException(
                status_code=404,
                detail=f"Job listings not found: {', '.join(missing_ids)}",
            )
        ordered_jobs = [jobs[listing_id] for listing_id in normalized_ids]
        for job in ordered_jobs:
            if job.platform != "official":
                raise HTTPException(
                    status_code=409,
                    detail=f"{job.platform} does not support apply batches.",
                )
        return ordered_jobs

    def _resolve_assets(self, db: Session, jobs: list[JobListing]) -> dict[str, dict[str, object]]:
        resolved: dict[str, dict[str, object]] = {}
        missing_accounts: list[str] = []
        missing_resumes: list[str] = []

        for job in jobs:
            company_key = resolve_company_key(
                source_company=job.source_company,
                source_site=job.source_site,
            )
            if not company_key:
                raise HTTPException(
                    status_code=409,
                    detail=f"Unsupported official company for apply batching: {job.source_company}",
                )
            account = official_asset_service.default_account_for_company(db, company_key)
            if not account:
                missing_accounts.append(job.source_company)
                continue
            binding = official_asset_service.binding_for_company(db, company_key)
            if not binding.default_resume_asset_id:
                missing_resumes.append(job.source_company)
                continue
            resume_asset = official_asset_service.get_resume_asset(
                db,
                binding.default_resume_asset_id,
            )
            resolved[job.id] = {
                "company_key": company_key,
                "account": account,
                "resume_asset": resume_asset,
            }

        if missing_accounts or missing_resumes:
            details: list[str] = []
            if missing_accounts:
                details.append(
                    f"Missing default account: {', '.join(sorted(set(missing_accounts)))}"
                )
            if missing_resumes:
                details.append(
                    f"Missing default resume: {', '.join(sorted(set(missing_resumes)))}"
                )
            raise HTTPException(status_code=409, detail="; ".join(details))
        return resolved

    def _refresh_batch_summary(
        self,
        db: Session,
        batch_id: str,
        *,
        commit: bool = True,
    ) -> ApplyBatch | None:
        batch = db.get(ApplyBatch, batch_id)
        if not batch:
            return None
        items = self.list_batch_items(db, batch_id)
        completed_items = sum(1 for item in items if item.status in FINAL_ITEM_STATUSES)
        submitted_items = sum(1 for item in items if item.status == "submitted")
        batch.completed_items = completed_items
        batch.submitted_items = submitted_items

        statuses = {item.status for item in items}
        if not items:
            batch.status = "failed"
            batch.message = "Apply batch contains no items."
        elif "needs_verification" in statuses:
            batch.status = "needs_verification"
            batch.message = "Manual verification is required before continuing."
        elif statuses <= {"submitted"}:
            batch.status = "submitted"
            batch.message = "All apply items were auto-submitted."
        elif statuses <= {"prepared", "submitted"}:
            batch.status = "prepared"
            batch.message = "Apply items are prepared and stopped before final submit."
        elif statuses <= {"failed"}:
            batch.status = "failed"
            batch.message = "Apply batch failed."
        elif statuses <= {"cancelled"}:
            batch.status = "cancelled"
            batch.message = "Apply batch was cancelled."
        elif statuses <= FINAL_ITEM_STATUSES:
            batch.status = "prepared"
            batch.message = "Apply batch finished with mixed outcomes."
        else:
            batch.status = "running"
            batch.message = "Apply batch is running."

        batch.updated_at = datetime.utcnow()
        db.add(batch)
        if commit:
            db.commit()
            db.refresh(batch)
        return batch

    def _normalize_mode(self, execution_mode: str) -> str:
        normalized = (execution_mode or "").strip()
        if normalized not in {"semi_auto", "auto_submit"}:
            raise HTTPException(status_code=400, detail="Unsupported apply execution mode.")
        return normalized


apply_batch_service = ApplyBatchService()
