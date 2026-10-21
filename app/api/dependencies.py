from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from ..core.security import authenticated_email
from ..db.models import User
from ..db.session import get_db


def get_current_user_email(
    request: Request,
    db: Session = Depends(get_db),
) -> str:
    email = authenticated_email(request)
    if email is None:
        raise HTTPException(status_code=401, detail="Sign-in required.")

    if db.get(User, email) is None:
        raise HTTPException(status_code=401, detail="Sign-in required.")
    return email
