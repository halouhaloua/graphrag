import json

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List
from app.database import get_db, AsyncSessionLocal
from rag.chat_history.schema import (
    ChatConversationCreate,
    ChatMessageCreate,
    ChatConversationResponse,
    ChatMessageResponse,
    ChatRequest,
)
from rag.chat_history.service import (
    ChatConversationService,
    ChatMessageService,
    ChatConversation,
)
from rag.graph_manager.service import ask_file_question_stream
from rag.kb_manager.db_service import KnowledgeBaseFileService
from rag.kb_manager.service import KnowledgeBasePermissionService
from utils.security import get_current_user
from core.user.model import User

router = APIRouter(prefix="/chat", tags=["聊天记录增删改查"])


@router.post("/conversation/create", response_model=ChatConversationResponse)
async def create_conversation(
    data: ChatConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv_data = ChatConversationCreate(
        title=data.title,
        user_id=user.id,
        model_name=data.model_name,
    )
    return await ChatConversationService.create(db, conv_data)


@router.get("/conversations", response_model=List[ChatConversationResponse])
async def get_user_conversations(
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = await ChatConversationService.get_user_conversations(
        db, user.id, page, page_size
    )
    return items


@router.get("/history/{conversation_id}", response_model=List[ChatMessageResponse])
async def get_chat_history(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await ChatConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return await ChatMessageService.get_messages_by_conversation(db, conversation_id)


@router.delete("/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await ChatConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    success = await ChatConversationService.delete(db, conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    return {"msg": "删除成功"}


async def _sse_stream_with_persistence(req: ChatRequest, conversation_id: str, user_id: str):
    answer_parts: List[str] = []
    sub_questions = []
    retrieved_triples = []
    retrieved_chunks = []
    reasoning_steps = []
    visualization_data = {}

    async with AsyncSessionLocal() as kb_session:
        async for raw_event in ask_file_question_stream(
            req.file_id, req.question, user_id, kb_session
        ):
                if raw_event.startswith("data: "):
                    try:
                        data = json.loads(raw_event[6:])
                        if data["type"] == "token":
                            if data.get("phase") != "reasoning":
                                answer_parts.append(data["text"])
                        elif data["type"] == "metadata":
                            sub_questions = data.get("sub_questions", [])
                            retrieved_triples = data.get("triples", [])
                            retrieved_chunks = data.get("chunks", [])
                        elif data["type"] == "reasoning_steps":
                            reasoning_steps = data.get("data", {}).get("reasoning_steps", [])
                        elif data["type"] == "visualization":
                            visualization_data = data.get("data", {})
                        elif data["type"] == "done":
                            full_answer = data.get("answer", "".join(answer_parts))
                            ai_content = {
                                "answer": full_answer,
                                "sub_questions": sub_questions,
                                "retrieved_triples": retrieved_triples,
                                "retrieved_chunks": retrieved_chunks,
                                "reasoning_steps": reasoning_steps,
                                "visualization_data": visualization_data,
                            }
                            ai_msg = ChatMessageCreate(
                                conversation_id=conversation_id,
                                role="assistant",
                                content=json.dumps(ai_content, ensure_ascii=False),
                                model_name=req.model_name,
                            )
                            async with AsyncSessionLocal() as sess:
                                await ChatMessageService.create(sess, ai_msg)
                            data["conversation_id"] = conversation_id
                            yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
                            continue
                    except json.JSONDecodeError:
                        pass
                yield raw_event


@router.post("/message/chat")
async def chat_completion(
    req: ChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    if not req.file_id:
        raise HTTPException(status_code=400, detail="file_id is required for graph-based chat")

    kb_file = await KnowledgeBaseFileService.get_by_id(db, req.file_id)
    if not kb_file:
        raise HTTPException(status_code=404, detail="文件不存在")
    if not await KnowledgeBasePermissionService.check_kb_access(db, kb_file.kb_id, user):
        raise HTTPException(status_code=403, detail="无权访问该知识库")

    if not req.conversation_id:
        conv_data = ChatConversationCreate(
            user_id=user.id,
            title=req.question[:20] + "...",
            model_name=req.model_name,
        )
        conv: ChatConversation = await ChatConversationService.create(db, conv_data)
        conversation_id = conv.id
    else:
        conv = await ChatConversationService.get_by_id(db, req.conversation_id)
        if not conv or conv.user_id != user.id:
            raise HTTPException(status_code=404, detail="会话不存在")
        conversation_id = req.conversation_id

    user_msg = ChatMessageCreate(
        conversation_id=conversation_id,
        role="user",
        content=req.question,
        model_name=req.model_name,
    )
    await ChatMessageService.create(db, user_msg)

    return StreamingResponse(
        _sse_stream_with_persistence(req, conversation_id, user.id),
        media_type="text/event-stream",
    )
