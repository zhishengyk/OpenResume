from __future__ import annotations

from datetime import datetime
import hashlib
from pathlib import Path
import re

from fastapi import HTTPException, UploadFile
from sqlmodel import Session, select

from ..models import CompanyBinding, OfficialAccount, OfficialSessionCache, ResumeAsset
from .credential_store import credential_store
from .official_sites import (
    default_resume_asset_path,
    default_storage_state_path,
    get_official_site,
    list_official_sites,
)


def _safe_filename(filename: str) -> str:
    name = Path(filename or "resume").name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)


class OfficialAssetService:
    def list_sites(self):
        return list_official_sites()

    def list_accounts(self, db: Session, *, company_key: str | None = None) -> list[OfficialAccount]:
        query = select(OfficialAccount).order_by(
            OfficialAccount.company_key,
            OfficialAccount.is_default.desc(),
            OfficialAccount.created_at.desc(),
        )
        if company_key:
            query = query.where(OfficialAccount.company_key == company_key)
        accounts = db.exec(query).all()
        for account in accounts:
            account.has_credentials = credential_store.has_password(account.credential_key)
        return accounts

    def get_account(self, db: Session, account_id: str) -> OfficialAccount:
        account = db.get(OfficialAccount, account_id)
        if not account:
            raise HTTPException(status_code=404, detail="Official account not found.")
        account.has_credentials = credential_store.has_password(account.credential_key)
        return account

    def upsert_account(
        self,
        db: Session,
        *,
        company_key: str,
        display_name: str,
        username: str,
        password: str | None,
        is_default: bool,
        account_id: str | None = None,
        status: str = "active",
    ) -> OfficialAccount:
        try:
            site = get_official_site(company_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Official company not found.") from error
        if account_id:
            account = self.get_account(db, account_id)
        else:
            account = OfficialAccount(company_key=company_key, company_name=site.company_name)

        account.company_key = company_key
        account.company_name = site.company_name
        account.display_name = (display_name or "").strip() or (username or "").strip()
        account.username = (username or "").strip()
        account.is_default = bool(is_default)
        account.status = (status or "active").strip() or "active"
        account.has_credentials = credential_store.has_password(account.credential_key)
        if password:
            credential_store.set_password(account.credential_key, password)
            account.has_credentials = True
        account.updated_at = datetime.utcnow()
        db.add(account)
        db.commit()
        db.refresh(account)

        if account.is_default:
            self._clear_other_default_accounts(
                db,
                company_key=company_key,
                keep_account_id=account.id,
            )

        self._ensure_session_cache(db, account)
        account.has_credentials = credential_store.has_password(account.credential_key)
        return account

    def delete_account(self, db: Session, account_id: str) -> None:
        account = self.get_account(db, account_id)
        cache = db.get(OfficialSessionCache, account.id)
        if cache:
            path = Path(cache.storage_state_path) if cache.storage_state_path else None
            if path and path.exists():
                path.unlink()
            db.delete(cache)
        credential_store.delete_password(account.credential_key)
        db.delete(account)
        db.commit()

    def list_session_caches(self, db: Session) -> list[OfficialSessionCache]:
        return db.exec(
            select(OfficialSessionCache).order_by(OfficialSessionCache.company_key)
        ).all()

    def list_resume_assets(self, db: Session) -> list[ResumeAsset]:
        return db.exec(
            select(ResumeAsset).order_by(ResumeAsset.created_at.desc())
        ).all()

    def get_resume_asset(self, db: Session, resume_asset_id: str) -> ResumeAsset:
        asset = db.get(ResumeAsset, resume_asset_id)
        if not asset:
            raise HTTPException(status_code=404, detail="Resume asset not found.")
        return asset

    async def save_resume_asset(
        self,
        db: Session,
        *,
        file: UploadFile,
        label: str | None = None,
    ) -> ResumeAsset:
        filename = file.filename or "resume.pdf"
        extension = Path(filename).suffix.lower()
        if extension not in {".pdf", ".docx"}:
            raise HTTPException(status_code=400, detail="Only PDF and DOCX resume assets are supported.")

        content = await file.read()
        digest = hashlib.sha256(content).hexdigest()
        safe_name = _safe_filename(filename)
        asset = ResumeAsset(
            label=(label or "").strip() or Path(filename).stem,
            source_filename=filename,
            storage_path="",
            mime_type=file.content_type or "",
            file_size=len(content),
            content_hash=digest,
        )
        db.add(asset)
        db.commit()
        db.refresh(asset)

        target_path = default_resume_asset_path(
            asset_id=asset.id,
            source_filename=safe_name,
        )
        target_dir = target_path.parent
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path.write_bytes(content)

        asset.storage_path = str(target_path)
        asset.updated_at = datetime.utcnow()
        db.add(asset)
        db.commit()
        db.refresh(asset)
        return asset

    def delete_resume_asset(self, db: Session, resume_asset_id: str) -> None:
        asset = self.get_resume_asset(db, resume_asset_id)
        for binding in db.exec(
            select(CompanyBinding).where(CompanyBinding.default_resume_asset_id == resume_asset_id)
        ).all():
            binding.default_resume_asset_id = None
            binding.updated_at = datetime.utcnow()
            db.add(binding)
        path = Path(asset.storage_path) if asset.storage_path else None
        if path and path.exists():
            path.unlink()
        db.delete(asset)
        db.commit()

    def list_company_bindings(self, db: Session) -> list[CompanyBinding]:
        bindings = {
            item.company_key: item
            for item in db.exec(select(CompanyBinding)).all()
        }
        results: list[CompanyBinding] = []
        for site in list_official_sites():
            binding = bindings.get(site.company_key)
            if not binding:
                binding = CompanyBinding(company_key=site.company_key)
            results.append(binding)
        return results

    def update_company_binding(
        self,
        db: Session,
        *,
        company_key: str,
        default_resume_asset_id: str | None,
    ) -> CompanyBinding:
        try:
            get_official_site(company_key)
        except KeyError as error:
            raise HTTPException(status_code=404, detail="Official company not found.") from error
        if default_resume_asset_id:
            self.get_resume_asset(db, default_resume_asset_id)
        binding = db.get(CompanyBinding, company_key) or CompanyBinding(company_key=company_key)
        binding.default_resume_asset_id = default_resume_asset_id
        binding.updated_at = datetime.utcnow()
        db.add(binding)
        db.commit()
        db.refresh(binding)
        return binding

    def default_account_for_company(self, db: Session, company_key: str) -> OfficialAccount | None:
        account = db.exec(
            select(OfficialAccount)
            .where(
                OfficialAccount.company_key == company_key,
                OfficialAccount.is_default == True,  # noqa: E712
            )
            .order_by(OfficialAccount.updated_at.desc())
        ).first()
        if account:
            account.has_credentials = credential_store.has_password(account.credential_key)
        return account

    def session_cache_for_account(self, db: Session, account_id: str) -> OfficialSessionCache | None:
        return db.get(OfficialSessionCache, account_id)

    def binding_for_company(self, db: Session, company_key: str) -> CompanyBinding:
        return db.get(CompanyBinding, company_key) or CompanyBinding(company_key=company_key)

    def mark_session_cache(
        self,
        db: Session,
        *,
        account_id: str,
        status: str,
        expires_at: datetime | None = None,
        last_success_at: datetime | None = None,
        last_verified_at: datetime | None = None,
    ) -> OfficialSessionCache:
        account = self.get_account(db, account_id)
        cache = self._ensure_session_cache(db, account)
        cache.status = status
        cache.expires_at = expires_at
        cache.last_success_at = last_success_at
        cache.last_verified_at = last_verified_at
        cache.updated_at = datetime.utcnow()
        db.add(cache)
        db.commit()
        db.refresh(cache)
        return cache

    def _ensure_session_cache(self, db: Session, account: OfficialAccount) -> OfficialSessionCache:
        cache = db.get(OfficialSessionCache, account.id)
        if cache:
            return cache
        cache = OfficialSessionCache(
            account_id=account.id,
            company_key=account.company_key,
            storage_state_path=str(
                default_storage_state_path(
                    company_key=account.company_key,
                    account_id=account.id,
                )
            ),
            status="missing",
        )
        db.add(cache)
        db.commit()
        db.refresh(cache)
        return cache

    def _clear_other_default_accounts(
        self,
        db: Session,
        *,
        company_key: str,
        keep_account_id: str,
    ) -> None:
        others = db.exec(
            select(OfficialAccount).where(
                OfficialAccount.company_key == company_key,
                OfficialAccount.id != keep_account_id,
                OfficialAccount.is_default == True,  # noqa: E712
            )
        ).all()
        changed = False
        for item in others:
            item.is_default = False
            item.updated_at = datetime.utcnow()
            db.add(item)
            changed = True
        if changed:
            db.commit()


official_asset_service = OfficialAssetService()
