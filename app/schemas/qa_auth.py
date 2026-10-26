from typing import Annotated, Literal

from pydantic import BaseModel, EmailStr, StringConstraints

UserRole = Literal["ADMIN", "QA_MANAGER", "QA_ENGINEER", "DEVELOPER", "VIEWER"]
Username = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True,
        min_length=3,
        max_length=32,
        pattern=r"^[A-Za-z0-9_.-]+$",
    ),
]
Password = Annotated[str, StringConstraints(min_length=12, max_length=128)]


class UserProfile(BaseModel):
    id: str
    username: str
    name: str
    email: str
    roles: list[UserRole]
    avatarUrl: str = ""


class UserResponse(BaseModel):
    user: UserProfile


class RegistrationRequest(BaseModel):
    username: Username
    email: EmailStr
    password: Password


class PendingRegistration(BaseModel):
    id: str
    username: str
    email: EmailStr
    requestedAt: str | None


class PendingRegistrationsResponse(BaseModel):
    users: list[PendingRegistration]


class UserApprovalRequest(BaseModel):
    role: UserRole
