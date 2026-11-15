"""Test setup: a separate `<db>_test` database migrated with Alembic, local file storage,
and Celery tasks executed inline. Must configure env vars before any `app` import."""

import os
import tempfile
from pathlib import Path

_tmp = Path(tempfile.mkdtemp(prefix="analytica-test-"))
_base_url = os.environ.get(
    "DATABASE_URL", "postgresql+psycopg://analytica:analytica@localhost:5432/analytica"
)
_root, _, _dbname = _base_url.rpartition("/")
TEST_DB = f"{_dbname}_test"
os.environ.update(
    ENVIRONMENT="test",
    DATABASE_URL=f"{_root}/{TEST_DB}",
    STORAGE_BACKEND="local",
    LOCAL_STORAGE_DIR=str(_tmp / "storage"),
    CACHE_DIR=str(_tmp / "cache"),
    CELERY_EAGER="true",
    ANTHROPIC_API_KEY="",
)

import pytest  # noqa: E402
from sqlalchemy import create_engine, text  # noqa: E402

DB_AVAILABLE = True


def _prepare_database() -> None:
    admin = create_engine(f"{_root}/postgres", isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": TEST_DB})
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{TEST_DB}"'))
    admin.dispose()
    eng = create_engine(os.environ["DATABASE_URL"], isolation_level="AUTOCOMMIT")
    with eng.connect() as conn:
        conn.execute(text("DROP SCHEMA public CASCADE; CREATE SCHEMA public"))
    eng.dispose()

    from alembic.config import Config

    from alembic import command

    cfg = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[1] / "alembic"))
    command.upgrade(cfg, "head")


@pytest.fixture(scope="session")
def database():
    global DB_AVAILABLE
    try:
        _prepare_database()
    except Exception as exc:  # noqa: BLE001
        DB_AVAILABLE = False
        pytest.skip(f"PostgreSQL not available for integration tests: {exc}")
    yield


@pytest.fixture
def db_clean(database):
    yield
    from app.core.db import get_engine

    with get_engine().begin() as conn:
        tables = conn.scalars(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                "AND tablename <> 'alembic_version'"
            )
        ).all()
        conn.execute(text("TRUNCATE " + ", ".join(f'"{t}"' for t in tables) + " CASCADE"))
    from app.services import app_settings

    app_settings._cache["values"] = None


@pytest.fixture
def client(db_clean):
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app()) as c:
        yield c


def register(client, email="ada@example.com", password="correct-horse-1"):
    res = client.post(
        "/api/v1/auth/register", json={"email": email, "password": password, "display_name": "Ada"}
    )
    assert res.status_code == 201, res.text
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return register(client)


def upload_csv(client, headers, csv_text: str, name="data.csv", project_name="P"):
    p = client.post("/api/v1/projects", json={"name": project_name}, headers=headers).json()
    res = client.post(
        f"/api/v1/projects/{p['id']}/datasets",
        headers=headers,
        files={"file": (name, csv_text.encode(), "text/csv")},
    )
    assert res.status_code == 202, res.text
    job = client.get(f"/api/v1/jobs/{res.json()['job_id']}", headers=headers).json()
    assert job["status"] == "succeeded", job
    detail = client.get(f"/api/v1/projects/{p['id']}", headers=headers).json()
    return detail
