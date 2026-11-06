from sqlalchemy.orm import Session

from ..core.auth_utils import normalize_email
from ..db.models import User
from ..schemas.auth import UserSignInRequest


class InvalidCredentialsError(Exception):
    pass


def sign_in(db: Session, data: UserSignInRequest) -> User:
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
        raise InvalidCredentialsError
    return user


def get_user(db: Session, email: str) -> User | None:
    return db.get(User, email)
