import importlib
import sqlite3
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def application(tmp_path, monkeypatch):
    monkeypatch.setenv("DB_FILE", str(tmp_path / "test.db"))
    monkeypatch.setenv("COOKIE_SECURE", "true")
    monkeypatch.delenv("OLLAMA_BASE_URL", raising=False)
    sys.modules.pop("cardiomate", None)
    return importlib.import_module("cardiomate")


def account(username):
    return {"username": username, "password": "Only-for-testing-29!",
            "full_name": "Test User", "university": "Test University"}


def test_page_and_private_files(application):
    with TestClient(application.app, base_url="https://testserver") as client:
        page = client.get("/")
        assert page.status_code == 200 and "text/html" in page.headers["content-type"]
        assert 'const FASTAPI_URL = ""' in page.text
        assert client.get("/health").json()["ollama_configured"] is False
        for path in ("/cardiomate.py", "/cardiomate_history.db", "/data/cardiomate_history.db"):
            assert client.get(path).status_code == 404
        assert client.get("/history").status_code == 401
        assert client.post("/predict", json={}).status_code == 401


def test_auth_hash_logout_and_persistence(application):
    with TestClient(application.app, base_url="https://testserver") as client:
        payload = account("alpha")
        response = client.post("/register", json=payload)
        assert response.status_code == 200
        cookie = response.headers["set-cookie"].lower()
        assert all(flag in cookie for flag in ("httponly", "secure", "samesite=strict"))
        with sqlite3.connect(application.DB_FILE) as db:
            stored = db.execute("SELECT password FROM users").fetchone()[0]
        assert stored.startswith("pbkdf2_sha256$") and stored != payload["password"]
        assert client.post("/register", json=payload).status_code == 400
        assert client.get("/me").json()["user"]["username"] == "alpha"
        assert client.post("/logout").status_code == 200
        assert client.get("/me").status_code == 401
        assert client.post("/login", json={"username": "alpha", "password": "wrong"}).status_code == 401
    # A fresh client can sign in against persisted database state.
    with TestClient(application.app, base_url="https://testserver") as client:
        assert client.post("/login", json=payload).status_code == 200
        assert client.get("/me").status_code == 200


def test_simulation_and_history_isolation(application):
    with TestClient(application.app, base_url="https://testserver") as first, \
         TestClient(application.app, base_url="https://testserver") as second:
        assert first.post("/register", json=account("first")).status_code == 200
        result = first.post("/predict", json={"selected_lead": "V1"})
        assert result.status_code == 200
        assert result.json()["ai_source"] == "FASTAPI_HEURISTIC_FALLBACK"
        assert result.json()["selected_lead"] == "V1"
        assert len(first.get("/history").json()) == 1
        assert second.post("/register", json=account("second")).status_code == 200
        assert second.get("/history").json() == []
        assert first.get("/history?limit=-1").status_code == 422
