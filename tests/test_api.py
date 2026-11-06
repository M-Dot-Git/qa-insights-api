from datetime import datetime
import re
from types import SimpleNamespace
from unittest.mock import AsyncMock

import app.services.health as health_service
from app.main import app
from fastapi.testclient import TestClient

client = TestClient(app)


def test_health_check_returns_timestamp_and_random_message() -> None:
    response = client.get("/health", headers={"Origin": "http://testserver"})

    assert response.status_code == 200
    result = response.json()
    assert set(result) == {"server_time", "message"}
    datetime.fromisoformat(result["server_time"].replace("Z", "+00:00"))
    assert result["message"].startswith("QA Insights API is healthy: ")
    assert re.fullmatch(r"[a-z0-9]{10}", result["message"].rsplit(" ", 1)[-1])


def test_root_does_not_serve_a_frontend() -> None:
    response = client.get("/")

    assert response.status_code == 404


def test_agent_health_calls_agent_with_random_prompt_when_body_is_missing(
    monkeypatch,
) -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Hello!"))],
            dict=lambda: {},
        )
    )
    close = AsyncMock()
    client_instance = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        close=close,
    )
    monkeypatch.setattr(health_service, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(health_service, "AsyncOpenAI", lambda **_: client_instance)

    response = client.post(
        "/health/agent",
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 200
    assert response.json()["healthy"] is True
    assert response.json()["agent_response"] == "Hello!"
    prompt = create.await_args.kwargs["messages"][-1]["content"]
    assert prompt
    close.assert_awaited_once()


def test_agent_health_sends_request_text_to_agent(monkeypatch) -> None:
    create = AsyncMock(
        return_value=SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content="Yes."))],
            dict=lambda: {},
        )
    )
    client_instance = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create)),
        close=AsyncMock(),
    )
    monkeypatch.setattr(health_service, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(health_service, "AsyncOpenAI", lambda **_: client_instance)

    response = client.post(
        "/health/agent",
        json={"text": "Check this prompt"},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 200
    assert create.await_args.kwargs["messages"][-1]["content"] == "Check this prompt"


def test_agent_health_returns_unavailable_when_api_key_is_missing(monkeypatch) -> None:
    monkeypatch.setattr(health_service, "OPENROUTER_API_KEY", "")

    response = client.post(
        "/health/agent",
        json={"text": "Are you available?"},
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 503
    assert response.json()["healthy"] is False


def test_state_change_requires_origin() -> None:
    response = client.post("/api/auth/logout")

    assert response.status_code == 403
    assert response.json() == {
        "error": "An origin header is required for this request."
    }


def test_same_origin_request_is_allowed() -> None:
    response = client.post(
        "/api/auth/logout",
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 204


def test_auth_code_endpoints_are_removed() -> None:
    response = client.get(
        "/api/auth/mode",
        headers={"Origin": "http://testserver"},
    )

    assert response.status_code == 404


def test_email_and_dob_sign_in_route_is_registered() -> None:
    paths = app.openapi()["paths"]
    assert "post" in paths["/api/auth/sign-in"]


def test_untrusted_origin_is_rejected() -> None:
    response = client.post(
        "/api/auth/logout",
        headers={"Origin": "https://untrusted.example"},
    )

    assert response.status_code == 403
    assert response.json() == {"error": "Cross-origin requests are not allowed."}


def test_oversized_content_length_is_rejected_before_parsing() -> None:
    response = client.post(
        "/api/auth/logout",
        headers={
            "Origin": "http://localhost:5173",
            "Content-Length": str(32 * 1024 * 1024 + 1),
        },
    )

    assert response.status_code == 413
    assert response.json() == {"error": "The request is too large."}
