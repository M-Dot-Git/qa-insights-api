from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from ...db.session import get_db
from ...schemas.chat import (
    ChatCreatedResponse,
    ChatListResponse,
    ChatResponse,
    ChatTurnRequest,
    CreateChatRequest,
)
from ...services import chats as chat_service
from ..dependencies import get_current_user_email

router = APIRouter(prefix="/api/chats", tags=["chats"])


@router.get("", response_model=ChatListResponse)
def list_chats(
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> dict:
    return chat_service.list_chats(db, email)


@router.post("", status_code=201, response_model=ChatCreatedResponse)
def create_chat(
    data: CreateChatRequest,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> dict:
    return chat_service.create_chat(db, email, data)


@router.get("/{chat_id}", response_model=ChatResponse)
def get_chat(
    chat_id: str,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> dict:
    return chat_service.get_chat(db, email, chat_id)


@router.post("/{chat_id}/turns")
def create_turn(
    chat_id: str,
    data: ChatTurnRequest,
    request: Request,
    email: str = Depends(get_current_user_email),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    return chat_service.create_turn_stream(chat_id, data, request, email, db)
