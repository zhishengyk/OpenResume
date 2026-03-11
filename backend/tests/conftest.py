import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlmodel import Session, SQLModel, create_engine

os.environ.setdefault("OPENRESUME_DISABLE_BROWSER_OPEN", "1")
TEST_STORAGE = Path(__file__).resolve().parent / ".test-storage"
TEST_STORAGE.mkdir(parents=True, exist_ok=True)
os.environ.setdefault("OPENRESUME_STORAGE_DIR", str(TEST_STORAGE))
TEST_DB_PATH = TEST_STORAGE / "test.db"

import openresume_api.db as db_module
from openresume_api.db import get_session
from openresume_api.main import app
from openresume_api.services.runtime_config import runtime_config_service


TEST_ENGINE = create_engine(
    f"sqlite:///{TEST_DB_PATH}",
    connect_args={"check_same_thread": False},
)
db_module.engine = TEST_ENGINE
SQLModel.metadata.create_all(TEST_ENGINE, checkfirst=True)


def override_get_session():
    with Session(TEST_ENGINE) as session:
        yield session


app.dependency_overrides[get_session] = override_get_session


@pytest.fixture(autouse=True)
def reset_database():
    TEST_ENGINE.dispose()
    if TEST_DB_PATH.exists():
        TEST_DB_PATH.unlink()
    SQLModel.metadata.create_all(TEST_ENGINE, checkfirst=True)
    if runtime_config_service.config_path.exists():
        runtime_config_service.config_path.unlink()
    yield


@pytest.fixture
def client():
    with TestClient(app) as test_client:
        yield test_client
