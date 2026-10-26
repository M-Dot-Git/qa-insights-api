"""Keycloak Admin REST API operations for user registration and approval."""

import logging
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterator
from urllib.parse import quote

import httpx

from .config import (
    KEYCLOAK_ADMIN_CLIENT_ID,
    KEYCLOAK_ADMIN_CLIENT_SECRET,
    KEYCLOAK_REALM,
    KEYCLOAK_URL,
)

logger = logging.getLogger(__name__)
PENDING_STATUS = "pending"


class KeycloakAdminError(Exception):
    """A safe-to-report Keycloak user-management failure."""


class DuplicateUserError(KeycloakAdminError):
    """The username or email already exists."""


class RegistrationNotFoundError(KeycloakAdminError):
    """The requested pending registration does not exist."""


class KeycloakAdminUnavailableError(KeycloakAdminError):
    """The API cannot use the configured Keycloak service account."""


def _admin_token(client: httpx.Client) -> str:
    if not KEYCLOAK_ADMIN_CLIENT_SECRET:
        raise KeycloakAdminUnavailableError(
            "Configure KEYCLOAK_ADMIN_CLIENT_SECRET for the Keycloak user-management client."
        )
    response = client.post(
        f"{KEYCLOAK_URL}/realms/{quote(KEYCLOAK_REALM, safe='')}/protocol/openid-connect/token",
        data={
            "grant_type": "client_credentials",
            "client_id": KEYCLOAK_ADMIN_CLIENT_ID,
            "client_secret": KEYCLOAK_ADMIN_CLIENT_SECRET,
        },
    )
    if response.is_error:
        logger.error("Keycloak service-account token request failed with status %s", response.status_code)
        raise KeycloakAdminUnavailableError(
            "Keycloak rejected the user-management service account. Check its client credentials and service-account roles."
        )
    payload = response.json()
    token = payload.get("access_token") if isinstance(payload, dict) else None
    if not isinstance(token, str) or not token:
        raise KeycloakAdminUnavailableError(
            "Keycloak did not return a user-management access token."
        )
    return token


def _admin_request(
    client: httpx.Client,
    token: str,
    method: str,
    path: str,
    *,
    json: dict[str, Any] | list[dict[str, Any]] | None = None,
    params: dict[str, str | int] | None = None,
) -> httpx.Response:
    response = client.request(
        method,
        f"{KEYCLOAK_URL}/admin/realms/{quote(KEYCLOAK_REALM, safe='')}/{path}",
        headers={"Authorization": f"Bearer {token}"},
        json=json,
        params=params,
    )
    if response.status_code == 409 and method == "POST" and path == "users":
        raise DuplicateUserError("A user with this username or email already exists.")
    if response.status_code == 404 and path.startswith("users/"):
        raise RegistrationNotFoundError("The pending registration was not found.")
    if response.status_code == 404:
        raise KeycloakAdminUnavailableError(
            "Keycloak could not find the configured role or management resource."
        )
    if response.is_error:
        logger.error(
            "Keycloak user-management request %s %s failed with status %s",
            method,
            path,
            response.status_code,
        )
        raise KeycloakAdminUnavailableError(
            "Keycloak could not complete the user-management request. Check the service-account roles."
        )
    return response


def create_pending_user(username: str, email: str, password: str) -> None:
    requested_at = datetime.now(timezone.utc).isoformat()
    representation = {
        "username": username,
        "email": email,
        "enabled": False,
        "emailVerified": False,
        "attributes": {
            "registrationStatus": [PENDING_STATUS],
            "registrationRequestedAt": [requested_at],
        },
        "credentials": [{"type": "password", "value": password, "temporary": False}],
    }
    try:
        with httpx.Client(timeout=10) as client:
            token = _admin_token(client)
            _admin_request(client, token, "POST", "users", json=representation)
    except httpx.HTTPError as error:
        logger.exception("Could not connect to the Keycloak user-management API")
        raise KeycloakAdminUnavailableError(
            "Could not connect to Keycloak user management. Try again later."
        ) from error


def list_pending_users() -> list[dict[str, str | None]]:
    users: list[dict[str, str | None]] = []
    first = 0
    page_size = 100
    try:
        with httpx.Client(timeout=10) as client:
            token = _admin_token(client)
            while True:
                response = _admin_request(
                    client,
                    token,
                    "GET",
                    "users",
                    params={"first": first, "max": page_size},
                )
                page = response.json()
                if not isinstance(page, list):
                    raise KeycloakAdminUnavailableError(
                        "Keycloak returned an invalid user list."
                    )
                for user in page:
                    if not isinstance(user, dict):
                        continue
                    attributes = user.get("attributes")
                    status = (
                        attributes.get("registrationStatus")
                        if isinstance(attributes, dict)
                        else None
                    )
                    if not isinstance(status, list) or PENDING_STATUS not in status:
                        continue
                    users.append(
                        {
                            "id": user.get("id") if isinstance(user.get("id"), str) else "",
                            "username": user.get("username")
                            if isinstance(user.get("username"), str)
                            else "",
                            "email": user.get("email")
                            if isinstance(user.get("email"), str)
                            else "",
                            "requestedAt": _first_attribute(
                                attributes, "registrationRequestedAt"
                            ),
                        }
                    )
                if len(page) < page_size:
                    break
                first += page_size
    except httpx.HTTPError as error:
        logger.exception("Could not connect to the Keycloak user-management API")
        raise KeycloakAdminUnavailableError(
            "Could not connect to Keycloak user management. Try again later."
        ) from error
    return users


def approve_user(user_id: str, role: str) -> None:
    with _user_management_client() as (client, token):
        user = _pending_user(client, token, user_id)
        role_response = _admin_request(
            client,
            token,
            "GET",
            f"roles/{quote(role, safe='')}",
        )
        role_representation = role_response.json()
        if not isinstance(role_representation, dict):
            raise KeycloakAdminUnavailableError("Keycloak returned an invalid role.")
        _admin_request(
            client,
            token,
            "POST",
            f"users/{quote(user_id, safe='')}/role-mappings/realm",
            json=[role_representation],
        )
        attributes = _registration_attributes(user, "approved")
        _admin_request(
            client,
            token,
            "PUT",
            f"users/{quote(user_id, safe='')}",
            json={"enabled": True, "attributes": attributes},
        )


def reject_user(user_id: str) -> None:
    with _user_management_client() as (client, token):
        user = _pending_user(client, token, user_id)
        _admin_request(
            client,
            token,
            "PUT",
            f"users/{quote(user_id, safe='')}",
            json={"enabled": False, "attributes": _registration_attributes(user, "rejected")},
        )


@contextmanager
def _user_management_client() -> Iterator[tuple[httpx.Client, str]]:
    try:
        with httpx.Client(timeout=10) as client:
            yield client, _admin_token(client)
    except httpx.HTTPError as error:
        logger.exception("Could not connect to the Keycloak user-management API")
        raise KeycloakAdminUnavailableError(
            "Could not connect to Keycloak user management. Try again later."
        ) from error


def _pending_user(client: httpx.Client, token: str, user_id: str) -> dict[str, Any]:
    response = _admin_request(
        client,
        token,
        "GET",
        f"users/{quote(user_id, safe='')}",
    )
    user = response.json()
    if not isinstance(user, dict):
        raise KeycloakAdminUnavailableError("Keycloak returned an invalid user record.")
    attributes = user.get("attributes")
    status = (
        attributes.get("registrationStatus")
        if isinstance(attributes, dict)
        else None
    )
    if not isinstance(status, list) or PENDING_STATUS not in status:
        raise RegistrationNotFoundError("The user does not have a pending registration.")
    return user


def _registration_attributes(user: dict[str, Any], status: str) -> dict[str, list[str]]:
    attributes = user.get("attributes")
    result = {
        name: [value for value in values if isinstance(value, str)]
        for name, values in attributes.items()
        if isinstance(name, str) and isinstance(values, list)
    } if isinstance(attributes, dict) else {}
    result["registrationStatus"] = [status]
    result["registrationReviewedAt"] = [datetime.now(timezone.utc).isoformat()]
    return result


def _first_attribute(attributes: dict[str, Any], name: str) -> str | None:
    value = attributes.get(name)
    return value[0] if isinstance(value, list) and value and isinstance(value[0], str) else None
