from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ...core.auth_utils import normalize_email
from ...core.passwords import hash_password, verify_password
from ...core.security import (
    authenticated_qa_user_id,
    clear_qa_session,
    issue_qa_session,
)
from ...db.models import QAUser
from ...db.session import get_db
from ...schemas.qa_auth import QALoginRequest, QASignUpRequest, QAUserResponse

router = APIRouter(prefix="/api/qa/auth", tags=["QA authentication"])


def user_response(user: QAUser) -> dict:
    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "name": user.username,
            "email": user.email,
            "role": user.role,
            "avatarUrl": "",
        }
    }


def start_session(response: Response, user: QAUser) -> None:
    try:
        issue_qa_session(response, user.id)
    except RuntimeError as error:
        raise HTTPException(
            status_code=503,
            detail="Sign-in is temporarily unavailable.",
        ) from error


@router.post("/signup", status_code=201, response_model=QAUserResponse)
def sign_up(
    data: QASignUpRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    email = normalize_email(str(data.email))
    username = data.username.strip().lower()
    duplicate = (
        db.query(QAUser)
        .filter(or_(QAUser.email == email, QAUser.username == username))
        .first()
    )
    if duplicate is not None:
        raise HTTPException(
            status_code=409,
            detail="An account already exists with that email or username.",
        )

    user = QAUser(
        id=str(uuid4()),
        username=username,
        email=email,
        password_hash=hash_password(data.password),
        role="QA_MANAGER",
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="An account already exists with that email or username.",
        ) from error
    db.refresh(user)
    start_session(response, user)
    return user_response(user)


@router.post("/login", response_model=QAUserResponse)
def log_in(
    data: QALoginRequest,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    email = normalize_email(str(data.email))
    user = db.query(QAUser).filter(QAUser.email == email).first()
    if user is None or not verify_password(data.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    start_session(response, user)
    return user_response(user)


@router.get("/session", response_model=QAUserResponse)
def get_session(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> dict:
    user_id = authenticated_qa_user_id(request)
    user = db.get(QAUser, user_id) if user_id else None
    if user is None:
        clear_qa_session(response)
        raise HTTPException(status_code=401, detail="Sign-in required.")
    return user_response(user)


@router.post("/logout", status_code=204)
def log_out(response: Response) -> Response:
    clear_qa_session(response)
    response.status_code = 204
    return response
