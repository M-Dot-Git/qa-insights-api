from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ...core.auth_utils import normalize_email
from ...core.security import authenticated_email, clear_session, issue_session
from ...db.models import User
from ...db.session import get_db
from ...schemas.auth import UserResponse, UserSignInRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/sign-in", response_model=UserResponse)
def sign_in(
    data: UserSignInRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    email = normalize_email(str(data.email))
    user = db.get(User, email)

    if user is None:
        user = User(
            email=email,
            name=data.name,
            date_of_birth=data.dateOfBirth,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
    elif user.date_of_birth != data.dateOfBirth:
        raise HTTPException(
            status_code=401,
            detail="Authentication failed. Check your email and date of birth.",
        )

    try:
        issue_session(response, email)
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

    user = db.get(User, email)
    if user is None:
        clear_session(response)
        raise HTTPException(status_code=401, detail="Sign-in required.")
    return {"user": {"email": user.email, "name": user.name}}


@router.post("/logout", status_code=204)
def logout(response: Response) -> Response:
    clear_session(response)
    response.status_code = 204
    return response
