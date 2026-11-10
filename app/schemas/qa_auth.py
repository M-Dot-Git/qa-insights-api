from typing import Literal

from pydantic import BaseModel

UserRole = Literal["ADMIN", "QA_MANAGER", "QA_ENGINEER", "DEVELOPER", "VIEWER"]


class UserProfile(BaseModel):
    id: str
    username: str
    name: str
    email: str
    roles: list[UserRole]
    avatarUrl: str = ""


class UserResponse(BaseModel):
    user: UserProfile
