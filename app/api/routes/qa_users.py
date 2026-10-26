from fastapi import APIRouter, Depends, HTTPException, status

from ..qa_dependencies import require_roles
from ...core.keycloak import User
from ...core.keycloak_admin import (
    KeycloakAdminError,
    RegistrationNotFoundError,
    approve_user,
    list_pending_users,
    reject_user,
)
from ...schemas.qa_auth import (
    PendingRegistrationsResponse,
    UserApprovalRequest,
)

router = APIRouter(prefix="/api/qa/admin/users", tags=["QA user administration"])


@router.get("/pending", response_model=PendingRegistrationsResponse)
def get_pending_users(
    _: User = Depends(require_roles("ADMIN")),
) -> dict:
    try:
        return {"users": list_pending_users()}
    except KeycloakAdminError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error


@router.post("/{user_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
def approve_registration(
    user_id: str,
    data: UserApprovalRequest,
    _: User = Depends(require_roles("ADMIN")),
) -> None:
    try:
        approve_user(user_id, data.role)
    except KeycloakAdminError as error:
        raise HTTPException(
            status_code=404 if isinstance(error, RegistrationNotFoundError) else 503,
            detail=str(error),
        ) from error


@router.post("/{user_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
def reject_registration(
    user_id: str,
    _: User = Depends(require_roles("ADMIN")),
) -> None:
    try:
        reject_user(user_id)
    except KeycloakAdminError as error:
        raise HTTPException(
            status_code=404 if isinstance(error, RegistrationNotFoundError) else 503,
            detail=str(error),
        ) from error
