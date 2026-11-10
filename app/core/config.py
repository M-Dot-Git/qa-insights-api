"""Environment-backed application settings."""

import os

from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = (os.getenv("PSQL_STR") or os.getenv("DATABASE_URL") or "").strip()
SESSION_SECRET = os.getenv("SESSION_SECRET", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openrouter/free").strip()
OPENROUTER_MULTIMODAL_MODEL = os.getenv(
    "OPENROUTER_MULTIMODAL_MODEL", "google/gemini-2.5-flash"
).strip()
APP_ENV = os.getenv("APP_ENV", os.getenv("NODE_ENV", "development")).lower()
IS_PRODUCTION = APP_ENV == "production"

APP_ORIGIN = os.getenv("APP_ORIGIN", "")
KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8080").rstrip("/")
KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "qa-pulse").strip()
KEYCLOAK_ISSUER = os.getenv(
    "KEYCLOAK_ISSUER", f"{KEYCLOAK_URL}/realms/{KEYCLOAK_REALM}"
).rstrip("/")
KEYCLOAK_JWKS_URL = os.getenv(
    "KEYCLOAK_JWKS_URL",
    f"{KEYCLOAK_ISSUER}/protocol/openid-connect/certs",
).strip()
KEYCLOAK_API_AUDIENCE = os.getenv(
    "KEYCLOAK_API_AUDIENCE", "qa-insights-api-admin"
).strip()
TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
SERVER_HOST = os.getenv("HOST", "127.0.0.1")
SERVER_PORT = int(os.getenv("PORT", "8000"))


def allowed_origins() -> set[str]:
    origins = [APP_ORIGIN, *TRUSTED_ORIGINS]
    if not IS_PRODUCTION:
        origins.extend(
            [
                "http://localhost:3000",
                "http://localhost:3001",
                "http://localhost:3002",
                "http://localhost:3003",
                "http://localhost:3004",
                "http://127.0.0.1:3000",
                "http://127.0.0.1:3001",
                "http://127.0.0.1:3002",
                "http://127.0.0.1:3003",
                "http://127.0.0.1:3004",
                "http://localhost:5173",
                "http://127.0.0.1:5173",
            ]
        )
    normalized: set[str] = set()
    for origin in filter(None, origins):
        normalized.add(normalize_origin(origin))
    if IS_PRODUCTION and not normalized:
        raise ValueError("Configure APP_ORIGIN with the public QA Insights API origin in production.")
    return normalized


def normalize_origin(origin: str) -> str:
    from urllib.parse import urlsplit

    parsed = urlsplit(origin)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid origin configured in APP_ORIGIN/TRUSTED_ORIGINS: {origin}")
    return f"{parsed.scheme}://{parsed.netloc}"
