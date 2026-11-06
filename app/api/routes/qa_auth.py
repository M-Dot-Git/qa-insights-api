from fastapi import APIRouter, Depends

from ...api.qa_dependencies import get_current_user
from ...core.keycloak import User
from ...schemas.qa_auth import UserResponse
from ...services.qa_auth import serialize_user

router = APIRouter(prefix="/api/qa/auth", tags=["QA authentication"])


@router.get("/session", response_model=UserResponse)
def get_session(current_user: User = Depends(get_current_user)) -> dict:
    return serialize_user(current_user)
