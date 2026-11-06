import httpx
from fastapi.testclient import TestClient

import app.services.test_reports_proxy as test_reports_proxy
from app.api.qa_dependencies import get_current_user
from app.core.keycloak import User
from app.main import app

client = TestClient(app)


def _override_current_user(monkeypatch) -> None:
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

    monkeypatch.setattr(test_reports_proxy, "TEST_REPORTS_API_URL", "http://reports:8001")
    monkeypatch.setattr(test_reports_proxy.httpx, "AsyncClient", MockAsyncClient)
    _override_current_user(monkeypatch)

    response = client.post(
        "/api/test-reports/reports?project=qa&tag=smoke&tag=nightly",
        content=b'{"name":"release"}',
        headers={
            "Authorization": "Bearer token",
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
        "authorization": "Bearer token",
        "content-type": "application/json",
    }


def test_test_reports_health_proxy_uses_service_health_path(monkeypatch) -> None:
    captured: dict[str, str] = {}

    class MockAsyncClient:
        def __init__(self, *, timeout: float) -> None:
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_: object) -> None:
            return None

        async def request(self, method: str, url: str, **kwargs: object) -> httpx.Response:
            captured["url"] = url
            return httpx.Response(
                200,
                json={"service": "qa-test-reports-api", "status": "ready"},
                request=httpx.Request(method, url),
            )

    monkeypatch.setattr(test_reports_proxy, "TEST_REPORTS_API_URL", "http://reports:8001")
    monkeypatch.setattr(test_reports_proxy.httpx, "AsyncClient", MockAsyncClient)
    _override_current_user(monkeypatch)

    response = client.get("/api/test-reports/health")

    assert response.status_code == 200
    assert captured["url"] == "http://reports:8001/health"
