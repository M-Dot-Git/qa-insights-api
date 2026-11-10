from fastapi import APIRouter, Depends

from ...api.qa_dependencies import get_current_user
from ...core.keycloak import User
from ...schemas.qa_auth import UserResponse

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
