from collections.abc import Generator
import jwt
import pytest
from fastapi.testclient import TestClient

import app.api.qa_dependencies as qa_dependencies
from app.core.keycloak import User
from app.main import app


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Generator[TestClient, None, None]:
    def user_from_token(token: str) -> User:
        if token == "invalid":
            raise jwt.InvalidTokenError("invalid token")
        roles = {
            "admin": frozenset({"ADMIN"}),
            "manager": frozenset({"QA_MANAGER"}),
            "engineer": frozenset({"QA_ENGINEER"}),
            "viewer": frozenset({"VIEWER"}),
            "unassigned": frozenset(),
        }.get(token)
        if roles is None:
            raise jwt.InvalidTokenError("invalid token")
        return User(
            subject=f"subject-{token}",
            username=f"user-{token}",
            name=f"User {token}",
            email=f"{token}@example.com",
            roles=roles,
        )

    monkeypatch.setattr(qa_dependencies, "user_from_access_token", user_from_token)
    with TestClient(app) as test_client:
        yield test_client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_session_requires_bearer_access_token(client: TestClient) -> None:
    assert client.get("/api/qa/auth/session").status_code == 401

    invalid = client.get("/api/qa/auth/session", headers=bearer("invalid"))
    assert invalid.status_code == 401
    assert invalid.headers["www-authenticate"] == "Bearer"


def test_session_returns_all_supported_realm_roles(client: TestClient) -> None:
    response = client.get("/api/qa/auth/session", headers=bearer("manager"))

    assert response.status_code == 200
    assert response.json() == {
        "user": {
            "id": "subject-manager",
            "username": "user-manager",
            "name": "User manager",
            "email": "manager@example.com",
            "roles": ["QA_MANAGER"],
            "avatarUrl": "",
        }
    }


def test_unassigned_user_has_no_role_and_cannot_open_test_explorer(
    client: TestClient,
) -> None:
    profile = client.get("/api/qa/auth/session", headers=bearer("unassigned"))
    assert profile.status_code == 200
    assert profile.json()["user"]["roles"] == []

    response = client.get("/api/qa/test-cases", headers=bearer("unassigned"))
    assert response.status_code == 403
    assert client.get("/api/qa/dashboard", headers=bearer("unassigned")).status_code == 403


def test_qa_engineer_can_use_qa_workflows(client: TestClient) -> None:
    profile = client.get("/api/qa/auth/session", headers=bearer("engineer"))
    assert profile.status_code == 200
    assert profile.json()["user"]["roles"] == ["QA_ENGINEER"]
    assert client.get("/api/qa/dashboard", headers=bearer("engineer")).status_code == 200
    assert client.get("/api/qa/test-cases", headers=bearer("engineer")).status_code == 200


def test_qa_endpoints_require_bearer_and_preserve_role_access(
    client: TestClient,
) -> None:
    assert client.get("/api/qa/dashboard").status_code == 401
    dashboard = client.get("/api/qa/dashboard", headers=bearer("manager"))
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

    cases = client.get("/api/qa/test-cases?status=Passed", headers=bearer("manager"))
    assert cases.status_code == 200
    assert all(case["status"] == "Passed" for case in cases.json()["items"])
    assert cases.json()["total"] == len(cases.json()["items"])
    assert client.get("/api/qa/test-cases/QA-001", headers=bearer("manager")).status_code == 200
    assert client.get("/api/qa/test-cases", headers=bearer("viewer")).status_code == 403


def test_test_case_catalog_is_in_memory(client: TestClient) -> None:
    from app.dummy_data.qa import TEST_CASES

    assert len(TEST_CASES) == 12
    assert all(case["id"].startswith("QA-") for case in TEST_CASES)


def test_registration_and_user_management_routes_are_not_exposed(
    client: TestClient,
) -> None:
    origin = {"Origin": "http://localhost:3000"}
    assert client.post("/api/qa/auth/register", headers=origin).status_code == 404
    assert client.get("/api/qa/admin/users/pending").status_code == 404
    assert client.post("/api/qa/admin/users/user-1/approve", headers=origin).status_code == 404
    assert client.post("/api/qa/admin/users/user-1/reject", headers=origin).status_code == 404
    assert client.get("/api/qa/admin/overview").status_code == 404
