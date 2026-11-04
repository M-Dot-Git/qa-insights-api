from ..core.keycloak import User

APPLICATION_ROLES = ("ADMIN", "QA_MANAGER", "QA_ENGINEER", "DEVELOPER", "VIEWER")


def serialize_user(current_user: User) -> dict:
    return {
        "user": {
            "id": current_user.subject,
            "username": current_user.username,
            "name": current_user.name,
            "email": current_user.email,
            "roles": [
                role for role in APPLICATION_ROLES if role in current_user.roles
            ],
            "avatarUrl": "",
        }
    }
