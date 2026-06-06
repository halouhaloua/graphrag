import json
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from loguru import logger

from agentscope.message import UserMsg, TextBlock, ToolResultBlock, ToolResultState
from agentscope.event import (
    TextBlockDeltaEvent,
    RequireExternalExecutionEvent,
    ExternalExecutionResultEvent,
    ReplyEndEvent,
)

from chronicle_writer.schema import ChronicleChatRequest
from chronicle_writer.agents.factory import create_main_agent
from chronicle_writer.workflow.state import ChronicleWritingState
from chronicle_writer.workflow.graph import build_chronicle_graph
from chronicle_writer.tools import set_active_kb_ids, init_tools
from chronicle_writer.model import ChronicleProject
from app.base_model import generate_nanoid
from app.config import settings


_NODE_LABELS: dict[str, str] = {
    "plan_project": "篇目规划",
    "decompose_only": "主题分解",
    "retrieve_aspect": "方面检索",
    "verify_evidence": "史料考证",
    "filter_relevance": "相关度审校",
    "write_sections_coord": "撰写准备",
    "write_section": "逐节撰写",
    "generate_appendix": "图表凡例",
    "compile_document": "统稿合成",
    "review_document": "校审核对",
    "quality_check": "质检归档",
    "finalize": "最终交付",
}


class ChronicleChatService:
    """基于主智能体的志书写作对话服务"""

    _graph = build_chronicle_graph()

    def __init__(self):
        self._last_state = None
        self._project_config: dict = {}

    async def chat(
        self, req: ChronicleChatRequest, user_id: str, db: AsyncSession
    ) -> AsyncGenerator[dict, None]:
        from app.database import AsyncSessionLocal
        from rag.ai_writer.model import (
            WriterMsgModel,
        )

        init_tools(lambda: AsyncSessionLocal())
        set_active_kb_ids(req.kb_ids)

        # ── 0. 确保对话 ──
        conversation_id = await self._ensure_conversation(req, user_id, db)

        # ── 0.5 保存用户消息 ──
        user_msg = WriterMsgModel(
            conversation_id=conversation_id,
            role="user",
            content=req.question,
            model_name=settings.LLM_MODEL,
        )
        db.add(user_msg)
        await db.commit()

        # ── 1. 主智能体 ──
        agent = create_main_agent()
        msg = UserMsg(name="user", content=req.question)

        project_id: str | None = None
        full_content = ""
        _workflow_completed = False
        _done_yielded = False

        async for event in agent.reply_stream(msg):
            # ── ① 对话文本流 → SSE token ──
            if isinstance(event, TextBlockDeltaEvent) and event.delta:
                full_content += event.delta
                yield {"type": "token", "text": event.delta}

            # ── ② ChronicleWriteTool 被调用 → 外部执行 LangGraph 工作流 ──
            elif isinstance(event, RequireExternalExecutionEvent):
                for tc in event.tool_calls:
                    yield {
                        "type": "status",
                        "stage": "writing_start",
                        "progress": 0.0,
                        "message": "开始志书写作...",
                    }

                    config = (
                        json.loads(tc.input) if isinstance(tc.input, str) else tc.input
                    )
                    self._project_config = config
                    project_id = await self._create_project(
                        config, user_id, conversation_id, db
                    )

                    _wf_errored = False
                    async for wf_event in self._execute_workflow(
                        project_id=project_id,
                        conversation_id=conversation_id,
                        config=config,
                        kb_ids=req.kb_ids,
                    ):
                        if wf_event.get("type") == "token":
                            full_content += wf_event.get("text", "")
                        if wf_event.get("type") == "error":
                            _wf_errored = True
                        yield wf_event

                    if _wf_errored:
                        # 工作流出错 → 不执行后续逻辑
                        continue

                    # 工作流完成 → 恢复智能体
                    result_event = ExternalExecutionResultEvent(
                        reply_id=event.reply_id,
                        execution_results=[
                            ToolResultBlock(
                                id=tc.id,
                                name=tc.name,
                                output=[
                                    TextBlock(
                                        text=json.dumps(
                                            {
                                                "status": "completed",
                                                "project_id": project_id,
                                            },
                                            ensure_ascii=False,
                                        )
                                    )
                                ],
                                state=ToolResultState.SUCCESS,
                            )
                        ],
                    )
                    final = await agent.reply(result_event)
                    if final and final.get_text_content():
                        full_content += final.get_text_content()
                        yield {
                            "type": "token",
                            "text": final.get_text_content(),
                        }

                    _workflow_completed = True
                    yield await self._build_done_event(project_id, conversation_id)
                    _done_yielded = True

            # ── ③ ReplyEnd → 保存 assistant 消息 + 结束 ──
            elif isinstance(event, ReplyEndEvent):
                # 保存 assistant 消息
                if _workflow_completed and project_id:
                    state = self._last_state or {}
                    sec_count = len(state.get("section_order", []))
                    word_count = sum(len(c) for c in state.get("sections", {}).values())
                    title = self._project_config.get("title", "志书")
                    summary = (
                        f"已完成《{title}》的撰写（{sec_count}节，{word_count}字）"
                    )
                else:
                    summary = full_content

                assistant_msg = WriterMsgModel(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=summary,
                    model_name=settings.LLM_MODEL,
                )
                db.add(assistant_msg)
                await db.commit()

                if not _done_yielded:
                    yield {
                        "type": "done",
                        "content": full_content,
                        "conversation_id": conversation_id,
                    }

    async def _ensure_conversation(
        self, req: ChronicleChatRequest, user_id: str, db: AsyncSession
    ) -> str:
        """获取或创建 WriterConversation，返回 conversation_id。"""
        from rag.ai_writer.model import WriterConvModel as WCM

        if req.conversation_id:
            stmt = select(WCM).where(
                WCM.id == req.conversation_id,
                WCM.user_id == user_id,
                WCM.is_deleted.is_(False),
            )
            result = await db.execute(stmt)
            conv = result.scalar_one_or_none()
            if conv:
                return conv.id

        conv = WCM(
            title=(req.question[:30] + "...")
            if len(req.question) > 30
            else req.question,
            model_name=settings.LLM_MODEL,
            user_id=user_id,
        )
        db.add(conv)
        await db.flush()
        await db.refresh(conv)
        return conv.id

    async def _create_project(
        self,
        config: dict,
        user_id: str,
        conversation_id: str,
        db: AsyncSession,
    ) -> str:
        pid = generate_nanoid()
        project = ChronicleProject(
            id=pid,
            conversation_id=conversation_id,
            title=config.get("title", ""),
            chronicle_type=config.get("chronicle_type", "town"),
            region_name=config.get("region_name", ""),
            scope_description=config.get("scope_description", ""),
            user_id=user_id,
            status="writing",
        )
        db.add(project)
        await db.commit()
        return pid

    async def _execute_workflow(
        self,
        project_id: str,
        conversation_id: str,
        config: dict,
        kb_ids: list[str],
    ) -> AsyncGenerator[dict, None]:
        import asyncio

        from chronicle_writer.event_queue import init_queue, clear_queue

        set_active_kb_ids(kb_ids)

        state = ChronicleWritingState(
            project_id=project_id,
            conversation_id=conversation_id,
            project_title=config.get("title", ""),
            chronicle_type=config.get("chronicle_type", "town"),
            region_name=config.get("region_name", ""),
            scope_description=config.get("scope_description", ""),
            kb_ids=kb_ids,
            file_ids=[],
            current_stage="planning",
            progress=0.0,
            status_message="开始写作...",
            outline=[],
            editorial_notes="",
            aspects=[],
            _aspect_names=[],
            _aspect_queries={},
            _aspect_idx=0,
            verified_data={},
            contradictions=[],
            filtered_data={},
            removed_items=[],
            sections={},
            section_order=[],
            _section_idx=0,
            current_section_idx=0,
            appendix_data={},
            review_results=[],
            quality_score=0.0,
            quality_checks=[],
            references=[],
            iteration_count=0,
            max_iterations=3,
            errors=[],
            report="",
            report_details=[],
            pending_events=[],
        )

        thread = {
            "configurable": {"thread_id": project_id, "recursion_limit": 50},
        }

        self._last_state = state

        queue: asyncio.Queue = asyncio.Queue()
        init_queue(queue)

        async def _run_graph():
            _emitted = 0
            try:
                async for event in self._graph.astream_events(
                    state, thread, version="v2"
                ):
                    kind = event["event"]
                    name = event["name"]
                    data = event.get("data", {})

                    if kind == "on_chain_start" and name in _NODE_LABELS:
                        label = _NODE_LABELS.get(name, name)
                        await queue.put(
                            {
                                "type": "node_start",
                                "node": name,
                                "label": label,
                            }
                        )

                    elif kind == "on_chain_stream" and name in _NODE_LABELS:
                        chunk = data.get("chunk") or {}
                        if isinstance(chunk, dict):
                            pending = chunk.get("pending_events") or []
                            for p in pending[_emitted:]:
                                await queue.put(p)
                            _emitted = len(pending)
                            self._last_state = chunk

                    elif kind == "on_chain_end" and name in _NODE_LABELS:
                        label = _NODE_LABELS.get(name, name)
                        output = data.get("output") or {}
                        progress = (
                            output.get("progress", 0) if isinstance(output, dict) else 0
                        )
                        await queue.put(
                            {
                                "type": "node_end",
                                "node": name,
                                "label": label,
                                "progress": progress,
                            }
                        )
            except Exception as e:
                logger.error(f"Workflow failed: {e}")
                await queue.put({"type": "error", "message": str(e)})
            finally:
                await queue.put(None)

        task = asyncio.create_task(_run_graph())

        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield event
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            clear_queue()

    def _serialize_kg_data(self, state: dict) -> dict:
        """从工作流状态中提取 KG 召回的三元组和 chunk 原文。"""
        aspects = state.get("aspects", [])
        if not aspects:
            return {}
        return {
            "aspects": [
                {
                    "name": a.get("name", ""),
                    "recall_query": a.get("recall_query", ""),
                    "triples": a.get("triples", [])[:20],
                    "chunks": a.get("chunks", [])[:5],
                    "triple_count": len(a.get("triples", [])),
                    "chunk_count": len(a.get("chunks", [])),
                }
                for a in aspects
            ],
            "removed_items": [
                {
                    "content": r.get("content", "")[:120],
                    "reason": r.get("reason", ""),
                }
                for r in (state.get("removed_items") or [])[:10]
            ],
        }

    async def _build_done_event(self, project_id: str, conversation_id: str) -> dict:
        state = self._last_state or {}
        sections = state.get("sections", {})
        section_order = state.get("section_order", [])
        content_parts = []
        for sid in section_order:
            txt = sections.get(sid, "")
            if txt:
                content_parts.append(txt)
        full_content = "\n\n".join(content_parts)
        word_count = sum(len(c) for c in sections.values())
        return {
            "type": "done",
            "project_id": project_id,
            "conversation_id": conversation_id,
            "word_count": word_count,
            "content": full_content,
            "sections": sections,
            "section_order": section_order,
            "report": state.get("report", ""),
            "report_details": state.get("report_details", []),
            "kg_data": self._serialize_kg_data(state),
        }
