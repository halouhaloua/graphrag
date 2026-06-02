import json

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from app.database import get_db, AsyncSessionLocal
from utils.security import get_current_user
from core.user.model import User

from rag.ai_writer.schema import (
    WriterConversationCreate,
    WriterConversationUpdate,
    WriterConversationResponse,
    WriterConversationListResponse,
    WriterMessageCreate,
    WriterMessageUpdate,
    WriterMessageResponse,
    WriterMessageListResponse,
    WriterDocumentCreate,
    WriterDocumentUpdate,
    WriterDocumentResponse,
    WriterDocumentListResponse,
    WriterChatRequest,
    WriterEditRequest,
    WriterMessageEditRequest,
)
from rag.ai_writer.service import (
    WriterConversationService,
    WriterMessageService,
    WriterDocumentService,
)
from rag.utils.call_llm_api import LLMCompletionCallStream

router = APIRouter(prefix="/api/ai-writing", tags=["AI 写作"])

SYSTEM_PROMPTS = {
    "chat": "你是一个专业的写作助手，可以帮助用户撰写、润色和改进文本内容。请根据用户的需求提供高质量的写作建议和内容创作。用和用户相同的语言回复。",
    "polish": "你是一个专业的文本润色助手。请润色以下文本，改进措辞、语法和表达，保持原意不变。直接输出润色后的完整内容，不要添加任何说明、解释或前缀。",
    "rewrite": "你是一个专业的文本改写助手。请用不同的表达方式重新表述以下文本，保持原意不变。直接输出改写后的完整内容，不要添加任何说明、解释或前缀。",
}


def _sse_event(data: dict) -> str:
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


# ─── Conversation CRUD ───


@router.post("/conversation/create", response_model=WriterConversationResponse)
async def create_conversation(
    data: WriterConversationCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from rag.ai_writer.model import WriterConversation as WriterConvModel
    conv = WriterConvModel(
        title=data.title or "新对话",
        model_name=data.model_name or "qwen",
        user_id=user.id,
    )
    db.add(conv)
    await db.commit()
    await db.refresh(conv)
    return conv


@router.get("/conversations", response_model=WriterConversationListResponse)
async def list_conversations(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200, alias="pageSize"),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    items, total = await WriterConversationService.get_user_conversations(
        db, user.id, page=page, page_size=page_size
    )
    return WriterConversationListResponse(items=items, total=total)


@router.get(
    "/conversation/{conversation_id}", response_model=WriterConversationResponse
)
async def get_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await WriterConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


@router.delete("/conversation/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await WriterConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")

    # cascade delete documents and messages
    docs = await WriterDocumentService.get_documents_by_conversation(db, conversation_id)
    for doc in docs:
        await WriterDocumentService.delete(db, doc.id, auto_commit=False)

    msgs = await WriterMessageService.get_messages_by_conversation(
        db, conversation_id
    )
    for msg in msgs:
        await WriterMessageService.delete(db, msg.id, auto_commit=False)

    success = await WriterConversationService.delete(db, conversation_id)
    if not success:
        raise HTTPException(status_code=404, detail="会话不存在")
    await db.commit()
    return {"msg": "删除成功"}


@router.put("/conversation/{conversation_id}/title")
async def update_conversation_title(
    conversation_id: str,
    data: WriterConversationUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await WriterConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    result = await WriterConversationService.update(
        db, conversation_id, data
    )
    if not result:
        raise HTTPException(status_code=404, detail="会话不存在")
    return result


# ─── Message CRUD ───


@router.get(
    "/conversation/{conversation_id}/messages",
    response_model=WriterMessageListResponse,
)
async def list_messages(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await WriterConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    items = await WriterMessageService.get_messages_by_conversation(
        db, conversation_id
    )
    return WriterMessageListResponse(items=items, total=len(items))


@router.put(
    "/conversation/{conversation_id}/message/{message_id}",
    response_model=WriterMessageResponse,
)
async def update_message(
    conversation_id: str,
    message_id: str,
    data: WriterMessageUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await WriterConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    msg = await WriterMessageService.get_by_id(db, message_id)
    if not msg or msg.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="消息不存在")
    updated = await WriterMessageService.update_message_content(
        db, message_id, data.content
    )
    if not updated:
        raise HTTPException(status_code=404, detail="消息不存在")
    await db.commit()
    await db.refresh(updated)
    return updated


# ─── SSE: AI Edit on a Message ───


@router.post(
    "/conversation/{conversation_id}/message/{message_id}/ai-edit",
    summary="AI 润色/改写指定消息（SSE 流式，自动更新 DB）",
)
async def ai_edit_message(
    conversation_id: str,
    message_id: str,
    req: WriterMessageEditRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await WriterConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    msg = await WriterMessageService.get_by_id(db, message_id)
    if not msg or msg.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="消息不存在")

    caller = LLMCompletionCallStream()

    if req.instruction == "custom":
        system_prompt = req.custom_prompt or "请按照用户的要求处理以下文本。"
    else:
        system_prompt = SYSTEM_PROMPTS.get(
            req.instruction, SYSTEM_PROMPTS["polish"]
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.content},
    ]

    async def generate():
        full_content = ""
        try:
            async for chunk in caller.call_api_stream_messages(
                messages, temperature=0.3
            ):
                full_content += chunk
                yield _sse_event({"type": "token", "text": chunk})
        except Exception as e:
            logger.error(f"AI edit message failed: {e}")
            yield _sse_event({"type": "error", "message": str(e)})
            yield "data: [DONE]\n\n"
            return

        # update message content in DB
        async with AsyncSessionLocal() as sess:
            msg = await WriterMessageService.get_by_id(sess, message_id)
            if msg:
                msg.content = full_content
                await sess.flush()

        yield _sse_event({"type": "done", "answer": full_content})
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ─── SSE: Chat ───


@router.post("/chat", summary="AI 写作对话（SSE 流式，自动保存到 DB）")
async def ai_chat(
    req: WriterChatRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    caller = LLMCompletionCallStream()

    # auto-create conversation if not provided
    if not req.conversation_id:
        from rag.ai_writer.model import WriterConversation as WriterConvModel
        conv = WriterConvModel(
            title=req.question[:20] + "...",
            model_name="qwen",
            user_id=user.id,
        )
        db.add(conv)
        await db.flush()
        conversation_id = conv.id
    else:
        conv = await WriterConversationService.get_by_id(db, req.conversation_id)
        if not conv or conv.user_id != user.id:
            raise HTTPException(status_code=404, detail="会话不存在")
        conversation_id = req.conversation_id

    # save user message
    user_msg = WriterMessageCreate(
        conversation_id=conversation_id,
        role="user",
        content=req.question,
    )
    await WriterMessageService.create(db, user_msg)

    messages = [{"role": "system", "content": SYSTEM_PROMPTS["chat"]}]
    if req.history:
        messages.extend(req.history)
    messages.append({"role": "user", "content": req.question})

    async def generate():
        full_content = ""
        # 预创建消息记录，确保流式完成后 DB 写入失败也有记录
        async with AsyncSessionLocal() as sess:
            assistant_msg = WriterMessageCreate(
                conversation_id=conversation_id,
                role="assistant",
                content="",
            )
            saved = await WriterMessageService.create(sess, assistant_msg)
        msg_id = saved.id

        try:
            async for chunk in caller.call_api_stream_messages(
                messages, temperature=0.7
            ):
                full_content += chunk
                yield _sse_event({"type": "token", "text": chunk})
        except Exception as e:
            logger.error(f"AI writing chat failed: {e}")
            async with AsyncSessionLocal() as sess:
                msg = await WriterMessageService.get_by_id(sess, msg_id)
                if msg:
                    msg.content = f"[Error] {e}"
                    await sess.flush()
            yield _sse_event({"type": "error", "message": str(e)})
            yield "data: [DONE]\n\n"
            return

        # 流式完成，更新消息内容
        async with AsyncSessionLocal() as sess:
            msg = await WriterMessageService.get_by_id(sess, msg_id)
            if msg:
                msg.content = full_content
                await sess.flush()

        yield _sse_event(
            {
                "type": "done",
                "answer": full_content,
                "conversation_id": conversation_id,
                "message_id": msg_id,
            }
        )
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")


# ─── Document CRUD ───


@router.post(
    "/conversation/{conversation_id}/message/{message_id}/document",
    response_model=WriterDocumentResponse,
    summary="创建文档（从AI消息转为文档编辑）",
)
async def create_document(
    conversation_id: str,
    message_id: str,
    data: WriterDocumentCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await WriterConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    msg = await WriterMessageService.get_by_id(db, message_id)
    if not msg or msg.conversation_id != conversation_id:
        raise HTTPException(status_code=404, detail="消息不存在")

    from rag.ai_writer.model import WriterDocument as WriterDocModel
    doc = WriterDocModel(
        conversation_id=conversation_id,
        message_id=message_id,
        title=data.title or "未命名文档",
        content=data.content,
    )
    db.add(doc)
    await db.commit()
    await db.refresh(doc)
    return doc


@router.get(
    "/conversation/{conversation_id}/documents",
    response_model=WriterDocumentListResponse,
    summary="获取对话的所有文档",
)
async def list_documents(
    conversation_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    conv = await WriterConversationService.get_by_id(db, conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    items = await WriterDocumentService.get_documents_by_conversation(
        db, conversation_id
    )
    return WriterDocumentListResponse(items=items, total=len(items))


@router.get(
    "/document/{document_id}",
    response_model=WriterDocumentResponse,
    summary="获取单个文档",
)
async def get_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await WriterDocumentService.get_by_id(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    conv = await WriterConversationService.get_by_id(db, doc.conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="文档不存在")
    return doc


@router.put(
    "/document/{document_id}",
    response_model=WriterDocumentResponse,
    summary="更新文档内容",
)
async def update_document(
    document_id: str,
    data: WriterDocumentUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await WriterDocumentService.get_by_id(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    conv = await WriterConversationService.get_by_id(db, doc.conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="文档不存在")
    updated = await WriterDocumentService.update_document(
        db, document_id, title=data.title, content=data.content
    )
    if not updated:
        raise HTTPException(status_code=404, detail="文档不存在")
    await db.commit()
    await db.refresh(updated)
    return updated


@router.delete("/document/{document_id}", summary="删除文档")
async def delete_document(
    document_id: str,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    doc = await WriterDocumentService.get_by_id(db, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="文档不存在")
    conv = await WriterConversationService.get_by_id(db, doc.conversation_id)
    if not conv or conv.user_id != user.id:
        raise HTTPException(status_code=404, detail="文档不存在")
    success = await WriterDocumentService.delete(db, document_id)
    if not success:
        raise HTTPException(status_code=404, detail="文档不存在")
    return {"msg": "文档删除成功"}


# ─── SSE: Standalone Edit (no persistence) ───


@router.post("/edit", summary="AI 润色/改写（SSE 流式，不入库）")
async def ai_edit(
    req: WriterEditRequest,
    user: User = Depends(get_current_user),
):
    caller = LLMCompletionCallStream()

    if req.instruction == "custom":
        system_prompt = req.custom_prompt or "请按照用户的要求处理以下文本。"
    else:
        system_prompt = SYSTEM_PROMPTS.get(
            req.instruction, SYSTEM_PROMPTS["polish"]
        )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": req.content},
    ]

    async def generate():
        full_content = ""
        try:
            async for chunk in caller.call_api_stream_messages(
                messages, temperature=0.3
            ):
                full_content += chunk
                yield _sse_event({"type": "token", "text": chunk})
        except Exception as e:
            logger.error(f"AI writing edit failed: {e}")
            yield _sse_event({"type": "error", "message": str(e)})
            yield "data: [DONE]\n\n"
            return

        yield _sse_event({"type": "done", "answer": full_content})
        yield "data: [DONE]\n\n"

    return StreamingResponse(generate(), media_type="text/event-stream")
