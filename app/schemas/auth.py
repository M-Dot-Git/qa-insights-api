from datetime import date

from pydantic import BaseModel, EmailStr, StringConstraints, field_validator
from typing import Annotated


class UserSignInRequest(BaseModel):
    email: EmailStr
    name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
    ]
    dateOfBirth: date

    @field_validator("dateOfBirth")
    @classmethod
    def birth_date_must_not_be_future(cls, value: date) -> date:
        if value > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        return value

class UserProfileResponse(BaseModel):
    email: EmailStr
    name: str


class UserResponse(BaseModel):
    user: UserProfileResponse
