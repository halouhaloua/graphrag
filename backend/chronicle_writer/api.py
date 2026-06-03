import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db
from utils.security import get_current_user
from core.user.model import User

from chronicle_writer.schema import ChronicleChatRequest
from chronicle_writer.service import ChronicleChatService

router = APIRouter(tags=["志书写作"])


def _sse(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/chat", summary="志书写作对话（SSE流式）")
async def chronicle_chat(
    req: ChronicleChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    service = ChronicleChatService()

    async def event_stream():
        try:
            async for event in service.chat(req, user.id, db):
                yield _sse(event)
                if event.get("type") in ("done", "error"):
                    break
        except Exception as e:
            logger.error(f"chat failed: {e}")
            yield _sse({"type": "error", "message": str(e)})
        yield "data: [DONE]\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")
