from types import SimpleNamespace

from starlette.responses import Response

import app.core.security as session


def test_session_token_uses_existing_jwt_cookie_format(monkeypatch) -> None:
    monkeypatch.setattr(session, "SESSION_SECRET", "s" * 40)
    response = Response()

    session.issue_session(response, "person@example.com")

    cookie = response.headers["set-cookie"]
    token = cookie.split(";", maxsplit=1)[0].split("=", maxsplit=1)[1]
    assert token.count(".") == 2
    assert session.authenticated_email(
        SimpleNamespace(cookies={session.COOKIE_NAME: token})
    ) == "person@example.com"


def test_invalid_session_token_is_rejected(monkeypatch) -> None:
    monkeypatch.setattr(session, "SESSION_SECRET", "s" * 40)

    assert session.authenticated_email(
        SimpleNamespace(cookies={session.COOKIE_NAME: "invalid"})
    ) is None
