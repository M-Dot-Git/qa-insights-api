from typing import Any

import httpx
import pytest

import app.core.keycloak_admin as keycloak_admin


class FakeKeycloakClient:
    responses: list[tuple[int, Any, dict[str, str]]]
    requests: list[tuple[str, str, dict[str, Any]]]

    def __init__(self, *, timeout: float) -> None:
        assert timeout == 10
        self.responses = []
        self.requests = []

    def __enter__(self):
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def post(self, url: str, *, data: dict[str, str]) -> httpx.Response:
        self.requests.append(("POST", url, data))
        return httpx.Response(
            200,
            json={"access_token": "service-account-token"},
            request=httpx.Request("POST", url),
        )

    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any] | list[dict[str, Any]] | None = None,
        params: dict[str, str | int] | None = None,
    ) -> httpx.Response:
        assert headers["Authorization"] == "Bearer service-account-token"
        self.requests.append((method, url, {"json": json, "params": params}))
        status_code, payload, response_headers = self.responses.pop(0)
        response_body = {"json": payload} if payload is not None else {"content": b""}
        return httpx.Response(
            status_code,
            headers=response_headers,
            request=httpx.Request(method, url),
            **response_body,
        )


@pytest.fixture
def fake_client(monkeypatch: pytest.MonkeyPatch) -> list[FakeKeycloakClient]:
    client = FakeKeycloakClient(timeout=10)
    monkeypatch.setattr(keycloak_admin.httpx, "Client", lambda **_kwargs: client)
    monkeypatch.setattr(keycloak_admin, "KEYCLOAK_ADMIN_CLIENT_SECRET", "test-secret")
    monkeypatch.setattr(keycloak_admin, "KEYCLOAK_ADMIN_CLIENT_ID", "qa-insights-api-admin")
    return [client]


def test_registration_creates_disabled_keycloak_user_with_password(
    fake_client: list[FakeKeycloakClient],
) -> None:
    client = fake_client[0]
    client.responses.append((201, None, {}))

    keycloak_admin.create_pending_user("new-user", "new@example.com", "long-test-password")

    request = client.requests[1]
    assert request[0] == "POST"
    assert request[1].endswith("/admin/realms/qa-pulse/users")
    body = request[2]["json"]
    assert body["enabled"] is False
    assert body["attributes"]["registrationStatus"] == ["pending"]
    assert body["credentials"] == [
        {"type": "password", "value": "long-test-password", "temporary": False}
    ]


def test_approval_assigns_role_before_enabling_account(
    fake_client: list[FakeKeycloakClient],
) -> None:
    client = fake_client[0]
    client.responses.extend(
        [
            (
                200,
                {"id": "user-1", "attributes": {"registrationStatus": ["pending"]}},
                {},
            ),
            (200, {"id": "QA_ENGINEER", "name": "QA_ENGINEER"}, {}),
            (204, None, {}),
            (204, None, {}),
        ]
    )

    keycloak_admin.approve_user("user-1", "QA_ENGINEER")

    role_mapping = client.requests[3]
    enable_user = client.requests[4]
    assert role_mapping[0] == "POST"
    assert role_mapping[1].endswith("/users/user-1/role-mappings/realm")
    assert role_mapping[2]["json"] == [{"id": "QA_ENGINEER", "name": "QA_ENGINEER"}]
    assert enable_user[0] == "PUT"
    assert enable_user[2]["json"]["enabled"] is True
    assert enable_user[2]["json"]["attributes"]["registrationStatus"] == ["approved"]


def test_rejected_user_remains_disabled_and_is_marked_rejected(
    fake_client: list[FakeKeycloakClient],
) -> None:
    client = fake_client[0]
    client.responses.extend(
        [
            (
                200,
                {"id": "user-1", "attributes": {"registrationStatus": ["pending"]}},
                {},
            ),
            (204, None, {}),
        ]
    )

    keycloak_admin.reject_user("user-1")

    update = client.requests[2]
    assert update[0] == "PUT"
    assert update[2]["json"]["enabled"] is False
    assert update[2]["json"]["attributes"]["registrationStatus"] == ["rejected"]


def test_pending_user_list_filters_keycloak_users(
    fake_client: list[FakeKeycloakClient],
) -> None:
    client = fake_client[0]
    client.responses.append(
        (
            200,
            [
                {
                    "id": "pending-1",
                    "username": "qa-1",
                    "email": "qa-1@gmail.com",
                    "attributes": {
                        "registrationStatus": ["pending"],
                        "registrationRequestedAt": ["2026-10-23T09:00:00Z"],
                    },
                },
                {
                    "id": "active-1",
                    "username": "active",
                    "email": "active@example.com",
                    "attributes": {"registrationStatus": ["approved"]},
                },
            ],
            {},
        )
    )

    pending = keycloak_admin.list_pending_users()

    assert pending == [
        {
            "id": "pending-1",
            "username": "qa-1",
            "email": "qa-1@gmail.com",
            "requestedAt": "2026-10-23T09:00:00Z",
        }
    ]
