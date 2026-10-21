"""Session-cookie signing and verification."""

import base64
import hashlib
import hmac
import json
import time

from fastapi import Request, Response

from .config import IS_PRODUCTION, SESSION_SECRET

COOKIE_NAME = "dazz_session"
QA_COOKIE_NAME = "qa_session"
SESSION_LIFETIME_SECONDS = 7 * 24 * 60 * 60


def _secret() -> bytes:
    if len(SESSION_SECRET) < 32 or SESSION_SECRET.startswith(
        "replace-with-a-random-secret"
    ):
        raise RuntimeError("SESSION_SECRET must be configured with at least 32 characters.")
    return SESSION_SECRET.encode()


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _issue_cookie(response: Response, subject: str, cookie_name: str) -> None:
    now = int(time.time())
    header = _b64(b'{"alg":"HS256","typ":"JWT"}')
    payload = _b64(
        json.dumps({"sub": subject, "iat": now, "exp": now + SESSION_LIFETIME_SECONDS}).encode()
    )
    signing_input = f"{header}.{payload}".encode()
    signature = _b64(hmac.new(_secret(), signing_input, hashlib.sha256).digest())
    token = f"{header}.{payload}.{signature}"
    response.set_cookie(
        cookie_name,
        token,
        max_age=SESSION_LIFETIME_SECONDS,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="strict",
        path="/",
    )


def _clear_cookie(response: Response, cookie_name: str) -> None:
    response.delete_cookie(
        cookie_name,
        httponly=True,
        secure=IS_PRODUCTION,
        samesite="strict",
        path="/",
    )


def _authenticated_subject(request: Request, cookie_name: str) -> str | None:
    token = request.cookies.get(cookie_name)
    if not token:
        return None
    try:
        header, payload, signature = token.split(".")
        if json.loads(base64.urlsafe_b64decode(header + "===")).get("alg") != "HS256":
            return None
        signing_input = f"{header}.{payload}".encode()
        expected = _b64(hmac.new(_secret(), signing_input, hashlib.sha256).digest())
        if not hmac.compare_digest(expected, signature):
            return None
        claims = json.loads(base64.urlsafe_b64decode(payload + "==="))
        if claims.get("exp", 0) <= int(time.time()):
            return None
        subject = claims.get("sub")
        return subject if isinstance(subject, str) else None
    except (ValueError, TypeError, KeyError, json.JSONDecodeError, RuntimeError):
        return None


def issue_session(response: Response, email: str) -> None:
    _issue_cookie(response, email, COOKIE_NAME)


def clear_session(response: Response) -> None:
    _clear_cookie(response, COOKIE_NAME)


def authenticated_email(request: Request) -> str | None:
    return _authenticated_subject(request, COOKIE_NAME)


def issue_qa_session(response: Response, user_id: str) -> None:
    _issue_cookie(response, user_id, QA_COOKIE_NAME)


def clear_qa_session(response: Response) -> None:
    _clear_cookie(response, QA_COOKIE_NAME)


def authenticated_qa_user_id(request: Request) -> str | None:
    return _authenticated_subject(request, QA_COOKIE_NAME)
