import json
import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse
from openai import AsyncOpenAI
from sqlalchemy.orm import Session

from ...core.config import (
    OPENROUTER_API_KEY,
    OPENROUTER_MODEL,
    OPENROUTER_MULTIMODAL_MODEL,
)
from ...db.models import PublicChat
from ...db.session import SessionLocal, get_db
from ...schemas.chat import (
    ChatCreatedResponse,
    ChatListResponse,
    ChatMessage,
    ChatResponse,
    ChatTurnRequest,
    CreateChatRequest,
)
from ..dependencies import get_current_user_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/chats", tags=["chats"])


def to_openrouter_message(message: ChatMessage) -> dict:
    if message.role == "assistant":
        return {"role": "assistant", "content": message.content}

    text_parts = [message.content.strip()] if message.content.strip() else []
    content: list[dict] = []
    for attachment in message.attachments:
        text_parts.append(f"Attached file: {attachment.name} ({attachment.mimeType}).")
        if attachment.transcript:
            text_parts.append(f"Voice transcript: {attachment.transcript}")
        if attachment.text:
            text_parts.append(f"Extracted text from {attachment.name}:\n{attachment.text}")
        if (
            attachment.mimeType.startswith(("image/", "audio/", "video/"))
            and not attachment.data
            and not attachment.frames
        ):
            text_parts.append(
                f"The media content of {attachment.name} is not included in this turn."
            )
    content.append({"type": "text", "text": "\n\n".join(text_parts)})
    for attachment in message.attachments:
        if attachment.data and attachment.mimeType.startswith("image/"):
            content.append(
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:{attachment.mimeType};base64,{attachment.data}"
                    },
                }
            )
        if attachment.data and attachment.format:
            content.append(
                {
                    "type": "input_audio",
                    "input_audio": {
                        "data": attachment.data,
                        "format": attachment.format,
                    },
                }
            )
        for index, frame in enumerate(attachment.frames, start=1):
            content.extend(
                [
                    {
                        "type": "text",
                        "text": f"Video frame {index} from {attachment.name}:",
                    },
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/jpeg;base64,{frame}"},
                    },
                ]
            )
    return {"role": "user", "content": content}


@router.get("", response_model=ChatListResponse)
def list_chats(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> dict:
    chats = (
        db.query(PublicChat)
        .filter(PublicChat.email == email)
        .order_by(PublicChat.updated_at.desc())
        .all()
    )
    return {
        "chats": [
            {"id": item.id, "title": item.title, "updatedAt": item.updated_at}
            for item in chats
        ]
    }


@router.post("", status_code=201, response_model=ChatCreatedResponse)
def create_chat(
    data: CreateChatRequest,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> dict:
    chat = PublicChat(id=str(uuid4()), email=email, title=data.title, messages=[])
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return {
        "chat": {"id": chat.id, "title": chat.title, "updatedAt": chat.updated_at}
    }


@router.get("/{chat_id}", response_model=ChatResponse)
def get_chat(
    chat_id: str,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> dict:
    chat = (
        db.query(PublicChat)
        .filter(PublicChat.id == chat_id, PublicChat.email == email)
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return {
        "chat": {
            "id": chat.id,
            "title": chat.title,
            "chats": chat.messages,
            "updatedAt": chat.updated_at,
        }
    }


@router.post("/{chat_id}/turns")
async def create_turn(
    chat_id: str,
    data: ChatTurnRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
):
    if str(data.chatId) != chat_id:
        raise HTTPException(status_code=400, detail="Invalid chat message.")
    if not OPENROUTER_API_KEY:
        raise HTTPException(
            status_code=500,
            detail="OPENROUTER_API_KEY is missing from the server environment.",
        )

    user_message = data.message
    chat = (
        db.query(PublicChat)
        .filter(PublicChat.id == chat_id, PublicChat.email == email)
        .with_for_update()
        .first()
    )
    if not chat:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    history = [*chat.messages, user_message.persistent()]
    chat.messages = history
    db.commit()
    current_messages = [
        ChatMessage.model_validate(message) for message in history[-41:-1]
    ]
    current_messages.append(user_message)
    uses_attachments = any(
        attachment.data or attachment.frames
        for message in current_messages
        for attachment in message.attachments
    )
    model = OPENROUTER_MULTIMODAL_MODEL if uses_attachments else OPENROUTER_MODEL

    async def event_stream():
        assistant_content = ""
        client = AsyncOpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=OPENROUTER_API_KEY,
            default_headers={
                "HTTP-Referer": "http://localhost:5173",
                "X-Title": "DAZZ",
            },
        )
        try:
            stream = await client.chat.completions.create(
                model=model,
                messages=[
                    {"role": "system", "content": "You are a helpful personal AI assistant."},
                    *(to_openrouter_message(message) for message in current_messages),
                ],
                stream=True,
            )  # ty: ignore[no-matching-overload]
            async for chunk in stream:
                if await request.is_disconnected():
                    return
                token = chunk.choices[0].delta.content
                if isinstance(token, str) and token:
                    assistant_content += token
                    yield json.dumps({"token": token}) + "\n"

            if SessionLocal is None:
                raise RuntimeError("Database session is unavailable.")
            with SessionLocal() as stream_db:
                latest = (
                    stream_db.query(PublicChat)
                    .filter(
                        PublicChat.id == chat_id,
                        PublicChat.email == email,
                    )
                    .with_for_update()
                    .first()
                )
                if latest:
                    latest.messages = [
                        *latest.messages,
                        {
                            "id": str(uuid4()),
                            "role": "assistant",
                            "content": assistant_content,
                        },
                    ]
                    stream_db.commit()
            yield json.dumps({"done": True}) + "\n"
        except Exception:
            logger.exception("OpenRouter chat stream failed")
            yield json.dumps(
                {
                    "error": "The assistant could not complete this response. Please try again."
                }
            ) + "\n"
        finally:
            await client.close()

    return StreamingResponse(
        event_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Accel-Buffering": "no",
        },
    )
