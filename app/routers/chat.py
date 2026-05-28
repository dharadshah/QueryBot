from fastapi import APIRouter
from app.schemas.chat import ChatRequest, ChatResponse
from app.schemas.user_context import UserContext
from app.services.chat_service import process_chat

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    user_context = UserContext()
    return process_chat(request=request, user_context=user_context)