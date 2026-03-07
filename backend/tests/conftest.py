import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("OPENRESUME_DISABLE_BROWSER_OPEN", "1")
os.environ.setdefault("OPENRESUME_BOSS_SEARCH_MODE", "fixture")
TEST_STORAGE = Path(__file__).resolve().parent / ".test-storage"
TEST_STORAGE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("OPENRESUME_STORAGE_DIR", str(TEST_STORAGE))

import openresume_api.db as db_module
from openresume_api.db import get_session
from openresume_api.main import app
from openresume_api.models import (
    AppSetting,
    ApplicationAttempt,
    CandidateProfile,
    JobListing,
    JobMatch,
    LLMAnalysisCache,
    RiskConsent,
    RiskEvent,
    SearchSession,
)


TEST_ENGINE = create_engine(
    f"sqlite:///{TEST_STORAGE / 'test.db'}",
    connect_args={"check_same_thread": False},
)
db_module.engine = TEST_ENGINE
SQLModel.metadata.create_all(TEST_ENGINE)


def override_get_session():
    with Session(TEST_ENGINE) as session:
        yield session


app.dependency_overrides[get_session] = override_get_session


@pytest.fixture(autouse=True)
def reset_database():
    SQLModel.metadata.drop_all(TEST_ENGINE)
    SQLModel.metadata.create_all(TEST_ENGINE)
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
