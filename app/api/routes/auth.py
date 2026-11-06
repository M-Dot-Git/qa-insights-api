from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ...core.security import authenticated_email, clear_session, issue_session
from ...db.session import get_db
from ...schemas.auth import UserResponse, UserSignInRequest
from ...services import auth as auth_service
from ...services.auth import InvalidCredentialsError

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/sign-in", response_model=UserResponse)
def sign_in(
    data: UserSignInRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    try:
        user = auth_service.sign_in(db, data)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=401,
            detail="Authentication failed. Check your email and date of birth.",
        )

    try:
        issue_session(response, user.email)
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail="Sign-in is temporarily unavailable.",
        ) from error
    return {"user": {"email": user.email, "name": user.name}}


@router.get("/session", response_model=UserResponse)
def get_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    email = authenticated_email(request)
    if email is None:
        clear_session(response)
        raise HTTPException(status_code=401, detail="Sign-in required.")

    user = auth_service.get_user(db, email)
    if user is None:
        clear_session(response)
        raise HTTPException(status_code=401, detail="Sign-in required.")
    return {"user": {"email": user.email, "name": user.name}}


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    clear_session(response)
    response.status_code = 204
    return response
