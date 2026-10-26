from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClientError

from ..core.keycloak import KeycloakUnavailableError, User, user_from_access_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> User:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="A valid Keycloak access token is required.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    try:
        return user_from_access_token(credentials.credentials)
    except KeycloakUnavailableError as error:
        raise HTTPException(
            status_code=503,
            detail="Keycloak authentication is temporarily unavailable.",
        ) from error
    except (InvalidTokenError, PyJWKClientError) as error:
        raise HTTPException(
            status_code=401,
            detail="The Keycloak access token is invalid or expired.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from error


def require_roles(*roles: str):
    def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.roles.isdisjoint(roles):
            raise HTTPException(status_code=403, detail="You do not have access to this resource.")
        return current_user

    return dependency
