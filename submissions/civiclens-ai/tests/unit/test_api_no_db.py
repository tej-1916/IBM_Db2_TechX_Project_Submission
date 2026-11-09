"""API tests that do not need a database (liveness, validation, 503 handling)."""

from fastapi.testclient import TestClient

from civiclens.api.deps import get_db
from civiclens.api.main import create_app


def test_health_is_db_independent():
    r = TestClient(create_app()).get("/api/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_db_health_returns_503_without_credentials(monkeypatch):
    from civiclens.config import Settings

    monkeypatch.delenv("DB2_PASSWORD", raising=False)
    monkeypatch.setitem(Settings.model_config, "env_file", None)  # ignore any local .env
    r = TestClient(create_app()).get("/api/health/db")
    assert r.status_code == 503
    assert "DB2_PASSWORD is not set" in r.json()["detail"]


def test_invalid_complaint_is_rejected_before_db():
    app = create_app()
    app.dependency_overrides[get_db] = lambda: None  # never reached for invalid bodies
    r = TestClient(app).post("/api/complaints", json={"category": "NOPE", "title": "x"})
    assert r.status_code == 422
