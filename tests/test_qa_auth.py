from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes.qa import TEST_CASES
from app.core import security
from app.db.models import QAUser
from app.db.session import get_db
from app.main import app

ORIGIN = {"Origin": "http://testserver"}
SIGN_UP = {
    "username": "Morgan.Lee",
    "email": "Morgan@example.com",
    "password": "correct-horse-battery-staple",
}


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    monkeypatch.setattr(security, "SESSION_SECRET", "test-secret-" + "x" * 40)
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    @event.listens_for(engine, "connect")
    def attach_qa_schema(connection, _record) -> None:
        connection.execute("ATTACH DATABASE ':memory:' AS qa_data")

    QAUser.__table__.create(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)

    def override_get_db() -> Generator[Session, None, None]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()
    engine.dispose()


def test_signup_hashes_password_and_sets_http_only_qa_cookie(client: TestClient) -> None:
    response = client.post("/api/qa/auth/signup", json=SIGN_UP, headers=ORIGIN)

    assert response.status_code == 201
    result = response.json()["user"]
    assert result["username"] == "morgan.lee"
    assert result["email"] == "morgan@example.com"
    assert result["role"] == "QA_MANAGER"
    assert "password" not in result
    cookie = response.headers["set-cookie"]
    assert "qa_session=" in cookie
    assert "httponly" in cookie.lower()
    assert "samesite=strict" in cookie.lower()

    database_session = client.app.dependency_overrides[get_db]()
    db = next(database_session)
    try:
        saved_user = db.query(QAUser).one()
        assert saved_user.password_hash != SIGN_UP["password"]
        assert saved_user.password_hash.startswith("scrypt$")
    finally:
        database_session.close()


def test_duplicate_signup_returns_conflict(client: TestClient) -> None:
    client.post("/api/qa/auth/signup", json=SIGN_UP, headers=ORIGIN)

    response = client.post(
        "/api/qa/auth/signup",
        json={**SIGN_UP, "username": "another-name"},
        headers=ORIGIN,
    )

    assert response.status_code == 409


def test_login_rejects_wrong_password_and_restores_session(client: TestClient) -> None:
    client.post("/api/qa/auth/signup", json=SIGN_UP, headers=ORIGIN)
    client.post("/api/qa/auth/logout", headers=ORIGIN)

    invalid = client.post(
        "/api/qa/auth/login",
        json={"email": SIGN_UP["email"], "password": "not-the-password"},
        headers=ORIGIN,
    )
    assert invalid.status_code == 401

    valid = client.post(
        "/api/qa/auth/login",
        json={"email": SIGN_UP["email"], "password": SIGN_UP["password"]},
        headers=ORIGIN,
    )
    assert valid.status_code == 200
    session = client.get("/api/qa/auth/session")
    assert session.status_code == 200
    assert session.json()["user"]["email"] == "morgan@example.com"


def test_logout_clears_qa_session_cookie(client: TestClient) -> None:
    client.post("/api/qa/auth/signup", json=SIGN_UP, headers=ORIGIN)

    response = client.post("/api/qa/auth/logout", headers=ORIGIN)

    assert response.status_code == 204
    assert "qa_session=" in response.headers["set-cookie"]
    assert client.get("/api/qa/auth/session").status_code == 401


def test_mock_qa_routes_require_a_session_and_return_expected_contract(
    client: TestClient,
) -> None:
    assert client.get("/api/qa/dashboard").status_code == 401
    client.post("/api/qa/auth/signup", json=SIGN_UP, headers=ORIGIN)

    dashboard = client.get("/api/qa/dashboard")
    assert dashboard.status_code == 200
    assert set(dashboard.json()) == {
        "generatedAt",
        "kpis",
        "trend",
        "releaseReadiness",
        "recentExecutions",
    }
    assert len(dashboard.json()["trend"]) == 7
    assert len(dashboard.json()["recentExecutions"]) == 6

    cases = client.get("/api/qa/test-cases?status=Passed")
    assert cases.status_code == 200
    assert all(case["status"] == "Passed" for case in cases.json()["items"])
    assert cases.json()["total"] == len(cases.json()["items"])
    assert client.get("/api/qa/test-cases/QA-001").status_code == 200


def test_mock_admin_route_requires_admin_role(client: TestClient) -> None:
    client.post("/api/qa/auth/signup", json=SIGN_UP, headers=ORIGIN)

    assert client.get("/api/qa/admin/overview").status_code == 403


def test_test_case_catalog_is_in_memory(client: TestClient) -> None:
    assert len(TEST_CASES) == 12
    assert all(case["id"].startswith("QA-") for case in TEST_CASES)
