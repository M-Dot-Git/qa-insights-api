from fastapi import APIRouter, Depends, HTTPException, status

from ...api.qa_dependencies import get_current_user
from ...core.keycloak import User
from ...core.keycloak_admin import (
    DuplicateUserError,
    KeycloakAdminError,
    create_pending_user,
)
from ...schemas.qa_auth import RegistrationRequest, UserResponse

router = APIRouter(prefix="/api/qa/auth", tags=["QA authentication"])

APPLICATION_ROLES = ("ADMIN", "QA_MANAGER", "QA_ENGINEER", "DEVELOPER", "VIEWER")


@router.get("/session", response_model=UserResponse)
def get_session(current_user: User = Depends(get_current_user)) -> dict:
    return {
        "user": {
            "id": current_user.subject,
            "username": current_user.username,
            "name": current_user.name,
            "email": current_user.email,
            "roles": [
                role for role in APPLICATION_ROLES if role in current_user.roles
            ],
            "avatarUrl": "",
        }
    }


@router.post("/register", status_code=status.HTTP_202_ACCEPTED)
def register(data: RegistrationRequest) -> dict[str, str]:
    try:
        create_pending_user(
            username=data.username.strip().lower(),
            email=str(data.email).strip().lower(),
            password=data.password,
        )
    except DuplicateUserError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except KeycloakAdminError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    return {"message": "Registration submitted. An administrator must approve your account."}
