from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.ai.chat_engine import answer
from app.ai.openai_client import stream_chat
from app.ai.prompts import CHAT_SYSTEM
from app.core.database import get_db
from app.core.deps import current_org
from app.core.rate_limit import hit
from app.models.tenant import Organization
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/chat", tags=["chat"])


@router.post("", response_model=ChatResponse)
def chat(payload: ChatRequest, db: Session = Depends(get_db),
         org: Organization = Depends(current_org)):
    hit(f"chat:{org.id}", limit=60, window_seconds=60)
    user_msg = next((m.content for m in reversed(payload.messages) if m.role == "user"), "")
    history = [
        m.model_dump() for m in payload.messages
        if m.role in ("user", "assistant")
    ][:-1]
    result = answer(
        db,
        organization_id=org.id,
        user_query=user_msg,
        use_web=payload.use_web,
        history=history,
    )
    return ChatResponse(**result)


@router.post("/stream")
def chat_stream(payload: ChatRequest, org: Organization = Depends(current_org)):
    """Streaming chat — SSE-friendly. Does NOT do tool calls; use POST /chat for grounded answers."""
    hit(f"chat:{org.id}", limit=120, window_seconds=60)
    messages = [{"role": "system", "content": CHAT_SYSTEM}]
    messages += [m.model_dump() for m in payload.messages]

    def gen():
        for token in stream_chat(messages):
            yield f"data: {token}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
