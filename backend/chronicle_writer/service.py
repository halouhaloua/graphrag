import json
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession
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

    async def chat(
        self, req: ChronicleChatRequest, user_id: str, db: AsyncSession
    ) -> AsyncGenerator[dict, None]:
        from app.database import AsyncSessionLocal

        init_tools(lambda: AsyncSessionLocal())
        set_active_kb_ids(req.kb_ids)

        agent = create_main_agent()
        msg = UserMsg(name="user", content=req.question)

        project_id = None
        _done_yielded = False

        async for event in agent.reply_stream(msg):
            if isinstance(event, TextBlockDeltaEvent) and event.delta:
                yield {"type": "token", "text": event.delta}

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
                    project_id = await self._create_project(config, user_id, db)

                    async for wf_event in self._execute_workflow(
                        project_id,
                        config,
                        req.kb_ids,
                    ):
                        yield wf_event

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
                        yield {"type": "token", "text": final.get_text_content()}

                    yield await self._build_done_event(project_id)
                    _done_yielded = True

            elif isinstance(event, ReplyEndEvent):
                if not _done_yielded:
                    yield {"type": "done", "content": ""}

    async def _create_project(
        self, config: dict, user_id: str, db: AsyncSession
    ) -> str:
        pid = generate_nanoid()
        project = ChronicleProject(
            id=pid,
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
        config: dict,
        kb_ids: list[str],
    ) -> AsyncGenerator[dict, None]:
        """执行 LangGraph 工作流，逐阶段 yield SSE 事件。

        使用 astream_events + asyncio.Queue 实现：
        - 节点边界（node_start/node_end）即时推送
        - write_section_node 内的 token 通过 event_queue 实时推送
        - 非 token 的 pending_events 在节点完成时通过 astream_events 推送
        """
        import asyncio

        from chronicle_writer.event_queue import init_queue, clear_queue

        set_active_kb_ids(kb_ids)

        state = ChronicleWritingState(
            project_id=project_id,
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
                await queue.put(None)  # sentinel

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

    async def _build_done_event(self, project_id: str) -> dict:
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
            "word_count": word_count,
            "content": full_content,
            "sections": sections,
            "section_order": section_order,
            "report": state.get("report", ""),
        }
