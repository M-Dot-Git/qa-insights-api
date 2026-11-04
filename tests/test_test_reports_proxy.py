import httpx
from fastapi.testclient import TestClient

import app.api.routes.test_reports as test_reports_route
from app.api.qa_dependencies import get_current_user
from app.core.keycloak import User
from app.main import app

client = TestClient(app)


def test_test_reports_proxy_requires_a_valid_keycloak_token() -> None:
    response = client.get(
        "/api/test-reports/health",
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 401


def test_test_reports_proxy_forwards_request_and_response(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class MockAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
            captured.update(method=method, url=url, **kwargs)
            request = httpx.Request(method, url)
            return httpx.Response(
                200,
                headers={"content-type": "application/json"},
                json={"service": "qa-test-reports-api", "status": "ready"},
                request=request,
            )

    monkeypatch.setattr(test_reports_route, "TEST_REPORTS_API_URL", "http://reports:8001")
    monkeypatch.setattr(test_reports_route.httpx, "AsyncClient", MockAsyncClient)
    monkeypatch.setitem(
        app.dependency_overrides,
        get_current_user,
        lambda: User(
            subject="subject",
            username="qa-engineer",
            name="QA Engineer",
            email="qa@example.com",
            roles=frozenset({"QA_ENGINEER"}),
        ),
    )

    response = client.post(
        "/api/test-reports/reports?project=qa&tag=smoke&tag=nightly",
        content=b'{"name":"release"}',
        headers={
            "Authorization": "Bearer test-access-token",
            "Content-Type": "application/json",
            "Origin": "http://testserver",
        },
    )

    assert response.status_code == 200
    assert response.json() == {
        "service": "qa-test-reports-api",
        "status": "ready",
    }
    assert captured["method"] == "POST"
    assert captured["url"] == "http://reports:8001/api/test-reports/reports"
    assert captured["params"] == [("project", "qa"), ("tag", "smoke"), ("tag", "nightly")]
    assert captured["content"] == b'{"name":"release"}'
    assert captured["headers"] == {
        "accept": "*/*",
        "authorization": "Bearer test-access-token",
        "content-type": "application/json",
    }
