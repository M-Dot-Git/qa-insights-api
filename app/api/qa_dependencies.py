from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from ..core.security import authenticated_qa_user_id, clear_qa_session
from ..db.models import QAUser
from ..db.session import get_db


def get_current_qa_user(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
) -> QAUser:
    user_id = authenticated_qa_user_id(request)
    user = db.get(QAUser, user_id) if user_id else None
    if user is None:
        clear_qa_session(response)
        raise HTTPException(status_code=401, detail="Sign-in required.")
    return user


def require_qa_roles(*roles: str):
    def dependency(user: QAUser = Depends(get_current_qa_user)) -> QAUser:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="You do not have access to this resource.")
        return user

    return dependency
