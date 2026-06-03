import asyncio
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


class ChronicleChatService:
    """基于主智能体的志书写作对话服务"""

    _graph = build_chronicle_graph()
    _decision_futures: dict[str, asyncio.Future] = {}

    def __init__(self):
        self._last_state = None

    async def chat(
        self, req: ChronicleChatRequest, user_id: str, db: AsyncSession
    ) -> AsyncGenerator[dict, None]:
        from app.database import AsyncSessionLocal

        init_tools(lambda: AsyncSessionLocal())
        set_active_kb_ids(req.kb_ids)

        # 处理中断决策（来自另一路 POST /chat）
        if req.interrupt_decision and req.conversation_id:
            pid = req.conversation_id
            future = self._decision_futures.get(pid)
            if future and not future.done():
                future.set_result(
                    {
                        "action": req.interrupt_decision.action,
                        "override_data": req.interrupt_decision.override_data,
                    }
                )
            else:
                # Future 还不存在 → 创建一个已完成的 Future 兼容竞态
                f = asyncio.get_event_loop().create_future()
                f.set_result(
                    {
                        "action": req.interrupt_decision.action,
                        "override_data": req.interrupt_decision.override_data,
                    }
                )
                self._decision_futures[pid] = f
            yield {"type": "decision_received", "message": "决策已提交"}
            return

        # 创建主智能体
        agent = create_main_agent()
        msg = UserMsg(name="user", content=req.question)

        project_id = None
        _done_yielded = False

        async for event in agent.reply_stream(msg):
            # ① 对话文本流 → SSE token
            if isinstance(event, TextBlockDeltaEvent) and event.delta:
                yield {"type": "token", "text": event.delta}

            # ② ChronicleWriteTool 被调用 → 外部执行 LangGraph 工作流
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
                        yield {"type": "token", "text": final.get_text_content()}

                    yield await self._build_done_event(project_id)
                    _done_yielded = True

            # ③ ReplyEnd → 结束 SSE（无工具调用的普通对话、或工具调用后的第二轮 reply）
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
        """执行 LangGraph 工作流，逐阶段 yield SSE 事件"""
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
            research_data={},
            global_facts=[],
            verified_data={},
            contradictions=[],
            human_decision=None,
            sections={},
            section_order=[],
            current_section_idx=0,
            appendix_data={},
            review_results=[],
            quality_score=0.0,
            quality_checks=[],
            references=[],
            iteration_count=0,
            max_iterations=3,
            errors=[],
            pending_events=[],
        )

        thread = {"configurable": {"thread_id": project_id}}
        config_lg = {"recursion_limit": 50}

        self._last_state = state

        try:
            async for update in self._graph.astream(state, thread, config=config_lg):
                self._last_state = update
                events = update.get("pending_events", [])
                for event in events:
                    yield event
                    if event["type"] == "interrupt":
                        yield {
                            "type": "status",
                            "stage": "waiting_human",
                            "progress": 0.35,
                            "message": "等待主编复核矛盾",
                        }
                        decision = await self._wait_for_decision(project_id)
                        state["human_decision"] = decision
                        break
        except Exception as e:
            logger.error(f"Workflow failed: {e}")
            yield {"type": "error", "message": str(e)}

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
        }

    async def _wait_for_decision(self, project_id: str) -> dict:
        future = self._decision_futures.get(project_id)
        if future is None or future.done():
            future = asyncio.get_event_loop().create_future()
            self._decision_futures[project_id] = future
        try:
            decision = await asyncio.wait_for(future, timeout=300)
            self._decision_futures.pop(project_id, None)
            return decision
        except asyncio.TimeoutError:
            self._decision_futures.pop(project_id, None)
            return {"action": "override"}
