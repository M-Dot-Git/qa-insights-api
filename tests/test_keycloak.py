from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import app.core.keycloak as keycloak


def install_signing_key(monkeypatch: pytest.MonkeyPatch, public_key) -> None:
    def resolve_signing_key(token: str):
        assert token
        return SimpleNamespace(key=public_key)

    def create_jwks_client(jwks_url: str):
        assert jwks_url.endswith("/protocol/openid-connect/certs")
        return SimpleNamespace(get_signing_key_from_jwt=resolve_signing_key)

    monkeypatch.setattr(
        keycloak,
        "_jwks_client",
        create_jwks_client,
    )


@pytest.fixture
def signing_keys(monkeypatch: pytest.MonkeyPatch):
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    install_signing_key(monkeypatch, private_key.public_key())
    return private_key


def access_token(private_key, **overrides: object) -> str:
    now = datetime.now(timezone.utc)
    claims = {
        "iss": "http://localhost:8080/realms/qa-pulse",
        "aud": "qa-insights-api",
        "sub": "keycloak-user-id",
        "iat": now,
        "exp": now + timedelta(minutes=5),
        "preferred_username": "qa-user",
        "realm_access": {"roles": ["QA_MANAGER"]},
    }
    claims.update(overrides)
    return jwt.encode(claims, private_key, algorithm="RS256", headers={"kid": "test-key"})


def test_decode_access_token_verifies_keycloak_claims(signing_keys) -> None:
    token = access_token(signing_keys)

    user = keycloak.user_from_access_token(token)

    assert user.subject == "keycloak-user-id"
    assert user.username == "qa-user"
    assert user.roles == frozenset({"QA_MANAGER"})


@pytest.mark.parametrize(
    "overrides",
    [
        {"iss": "http://localhost:8080/realms/other-realm"},
        {"aud": "another-api"},
        {"exp": datetime.now(timezone.utc) - timedelta(minutes=1)},
    ],
)
def test_decode_access_token_rejects_wrong_issuer_audience_or_expiry(
    signing_keys,
    overrides,
) -> None:
    token = access_token(signing_keys, **overrides)

    with pytest.raises(jwt.InvalidTokenError):
        keycloak.decode_access_token(token)


def test_decode_access_token_rejects_a_signature_from_another_key(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    trusted_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    install_signing_key(monkeypatch, trusted_key.public_key())
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    token = access_token(other_key)

    with pytest.raises(jwt.InvalidTokenError):
        keycloak.decode_access_token(token)
