"""Keycloak access-token verification."""

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient, PyJWKClientConnectionError, PyJWKClientError

from .config import KEYCLOAK_API_AUDIENCE, KEYCLOAK_ISSUER, KEYCLOAK_JWKS_URL


class KeycloakUnavailableError(Exception):
    """Raised when the API cannot retrieve Keycloak's signing keys."""


@dataclass(frozen=True)
class User:
    subject: str
    username: str
    name: str
    email: str
    roles: frozenset[str]


@lru_cache(maxsize=1)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    return PyJWKClient(jwks_url, cache_keys=True, timeout=5)


def decode_access_token(token: str) -> dict[str, Any]:
    if not KEYCLOAK_ISSUER or not KEYCLOAK_API_AUDIENCE:
        raise KeycloakUnavailableError("Keycloak issuer and audience must be configured.")

    issuer = KEYCLOAK_ISSUER
    try:
        signing_key = _jwks_client(KEYCLOAK_JWKS_URL).get_signing_key_from_jwt(token).key
    except PyJWKClientConnectionError as error:
        raise KeycloakUnavailableError("Could not retrieve Keycloak signing keys.") from error
    except PyJWKClientError as error:
        raise jwt.InvalidTokenError("The access token uses an unknown signing key.") from error

    claims = jwt.decode(
        token,
        signing_key,
        algorithms=["RS256"],
        audience=KEYCLOAK_API_AUDIENCE,
        issuer=issuer,
        leeway=30,
        options={"require": ["exp", "iat", "sub"]},
    )
    realm_access = claims.get("realm_access")
    roles = realm_access.get("roles", []) if isinstance(realm_access, dict) else []
    if not isinstance(roles, list) or not all(isinstance(role, str) for role in roles):
        roles = []

    subject = claims["sub"]
    username = claims.get("preferred_username")
    name = claims.get("name")
    email = claims.get("email")
    if not isinstance(subject, str) or not subject:
        raise jwt.InvalidTokenError("The access token has no subject.")
    if not isinstance(username, str):
        username = subject
    if not isinstance(name, str):
        name = username
    if not isinstance(email, str):
        email = ""

    return {
        "subject": subject,
        "username": username,
        "name": name,
        "email": email,
        "roles": frozenset(roles),
    }


def user_from_access_token(token: str) -> User:
    claims = decode_access_token(token)
    return User(**claims)
