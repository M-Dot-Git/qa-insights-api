from datetime import date, timedelta
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.api.routes.chats import to_openrouter_message
from app.db.base import Base
from app.db.models import PublicChat
from app.schemas.auth import UserSignInRequest
from app.schemas.chat import ChatMessage, ChatTurnRequest


def test_profile_rejects_future_birth_date() -> None:
    with pytest.raises(ValidationError):
        UserSignInRequest(
            email="person@example.com",
            name="Person",
            dateOfBirth=date.today() + timedelta(days=1),
        )


def test_turn_requires_user_content() -> None:
    with pytest.raises(ValidationError):
        ChatTurnRequest(
            chatId=uuid4(),
            message={
                "id": str(uuid4()),
                "role": "user",
                "content": "  ",
                "attachments": [],
            },
        )


def test_persisted_attachments_omit_upload_payloads() -> None:
    message = ChatMessage(
        id=uuid4(),
        role="user",
        content="Summarize this image",
        attachments=[
            {
                "id": "image-1",
                "name": "image.png",
                "mimeType": "image/png",
                "size": 10,
                "data": "base64-image",
                "frames": ["base64-frame"],
                "text": "recognized content",
            }
        ],
    )

    stored = message.persistent()

    assert stored["attachments"][0] == {
        "id": "image-1",
        "name": "image.png",
        "mimeType": "image/png",
        "size": 10,
        "text": "recognized content",
    }


def test_video_frames_are_included_for_model_but_not_storage() -> None:
    message = ChatMessage(
        id=uuid4(),
        role="user",
        content="Describe this clip",
        attachments=[
            {
                "id": "clip-1",
                "name": "clip.mp4",
                "mimeType": "video/mp4",
                "size": 10,
                "frames": ["frame-data"],
            }
        ],
    )

    request = to_openrouter_message(message)

    assert request["content"][-1]["image_url"]["url"] == "data:image/jpeg;base64,frame-data"
    assert "frames" not in message.persistent()["attachments"][0]


def test_sqlalchemy_models_map_existing_tables_without_otp_table() -> None:
    assert set(Base.metadata.tables) == {"users", "public_chats", "qa_data.users"}
    assert PublicChat.__table__.c.chats.name == "chats"
