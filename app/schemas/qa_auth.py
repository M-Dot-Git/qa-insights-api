from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, StringConstraints

QAUserRole = Literal["ADMIN", "QA_MANAGER", "DEVELOPER", "VIEWER"]

Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=32,
        pattern=r"^[A-Za-z0-9_.-]+$",
    ),
]
Password = Annotated[
    str,
    StringConstraints(min_length=12, max_length=128),
]


class QASignUpRequest(BaseModel):
    username: Username
    email: EmailStr
    password: Password


class QALoginRequest(BaseModel):
    email: EmailStr
    password: Password


class QAUserProfile(BaseModel):
    id: str
    username: str
    name: str
    email: EmailStr
    role: QAUserRole
    avatarUrl: str = ""


class QAUserResponse(BaseModel):
    user: QAUserProfile
